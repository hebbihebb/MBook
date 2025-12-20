"""
EPUB Parser with Chapter Awareness

Extracts text content from EPUB files while preserving chapter structure.
Used by the audiobook generator to create chapter markers in M4B output.
"""

import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
from dataclasses import dataclass, field
from typing import List, Optional
import re
import os
import tempfile
from pathlib import Path

from epub_validation import validate_epub_safe


@dataclass
class Chapter:
    """Represents a single chapter from an EPUB."""
    title: str
    content: str
    order: int


@dataclass
class ParsedEpub:
    """Complete parsed EPUB with metadata and chapters."""
    title: str
    author: str
    chapters: List[Chapter]
    cover_image: Optional[bytes] = None
    cover_media_type: Optional[str] = None


class EpubParser:
    def __init__(self, epub_path: str):
        self.epub_path = epub_path
        self.parsed_epub = parse_epub_with_chapters(epub_path)
        self.cover_image_path = None

    def get_book_title(self) -> str:
        return self.parsed_epub.title

    def get_book_author(self) -> str:
        return self.parsed_epub.author

    def get_chapters(self) -> List[Chapter]:
        return self.parsed_epub.chapters

    def get_cover_image_path(self) -> Optional[str]:
        if self.parsed_epub.cover_image and not self.cover_image_path:
            # Save the cover image to a temporary file
            ext = get_cover_extension(self.parsed_epub.cover_media_type)
            cover_filename = f"cover{ext}"
            cover_path = Path(tempfile.gettempdir()) / cover_filename
            with open(cover_path, "wb") as f:
                f.write(self.parsed_epub.cover_image)
            self.cover_image_path = str(cover_path)
        return self.cover_image_path


def clean_html_text(html_content: bytes) -> str:
    """Extract clean text from HTML content."""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Remove script and style elements
    for element in soup(['script', 'style', 'head', 'meta', 'link']):
        element.decompose()
    
    # Get text with some structure preservation
    text = soup.get_text(separator='\n')
    
    # Clean up whitespace
    lines = [line.strip() for line in text.splitlines()]
    text = '\n'.join(line for line in lines if line)
    
    return text


def extract_chapter_title(html_content: bytes, fallback_title: str) -> str:
    """Try to extract chapter title from HTML content."""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Look for heading elements
    for tag in ['h1', 'h2', 'h3']:
        heading = soup.find(tag)
        if heading:
            title = heading.get_text(strip=True)
            if title and len(title) < 100:  # Reasonable title length
                return title
    
    return fallback_title


def parse_epub_with_chapters(epub_path: str) -> ParsedEpub:
    """
    Parse an EPUB file and extract chapters with their content.
    
    Args:
        epub_path: Path to the EPUB file
        
    Returns:
        ParsedEpub object containing metadata and ordered chapters
    """
    # Security check for ZIP bombs
    validate_epub_safe(epub_path)

    book = epub.read_epub(epub_path)
    
    # Extract metadata
    title = book.title or "Unknown Title"
    
    # Get author - handle various metadata formats
    author = "Unknown Author"
    creators = book.get_metadata('DC', 'creator')
    if creators:
        author = creators[0][0]
    
    # Extract cover image if present
    cover_image = None
    cover_media_type = None
    
    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_COVER:
            cover_image = item.get_content()
            cover_media_type = item.media_type
            break
    
    # If no cover item, look for common cover image patterns
    if not cover_image:
        for item in book.get_items_of_type(ebooklib.ITEM_IMAGE):
            name = item.get_name().lower()
            if 'cover' in name:
                cover_image = item.get_content()
                cover_media_type = item.media_type
                break
    
    # Get spine order (reading order of documents)
    spine_ids = [item_id for item_id, _ in book.spine]
    
    # Create mapping from ID to item
    id_to_item = {}
    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            id_to_item[item.get_id()] = item
    
    # Try to get chapter titles from TOC (table of contents)
    toc_titles = {}
    
    def extract_toc_titles(toc_items, id_to_item_map):
        """Recursively extract titles from TOC."""
        for item in toc_items:
            if isinstance(item, tuple):
                # Nested TOC section
                section, children = item
                if hasattr(section, 'href') and hasattr(section, 'title'):
                    # Match href to item id
                    href = section.href.split('#')[0]  # Remove anchor
                    for item_id, doc_item in id_to_item_map.items():
                        if doc_item.get_name() == href or doc_item.get_name().endswith(href):
                            toc_titles[item_id] = section.title
                            break
                extract_toc_titles(children, id_to_item_map)
            elif hasattr(item, 'href') and hasattr(item, 'title'):
                href = item.href.split('#')[0]
                for item_id, doc_item in id_to_item_map.items():
                    if doc_item.get_name() == href or doc_item.get_name().endswith(href):
                        toc_titles[item_id] = item.title
                        break
    
    extract_toc_titles(book.toc, id_to_item)
    
    # Extract chapters in spine order
    chapters = []
    chapter_order = 0
    
    for spine_id in spine_ids:
        if spine_id not in id_to_item:
            continue
            
        item = id_to_item[spine_id]
        content = item.get_content()
        text = clean_html_text(content)
        
        # Skip empty or very short content (likely title pages, etc.)
        if len(text.strip()) < 50:
            continue
        
        # Get chapter title
        if spine_id in toc_titles:
            title = toc_titles[spine_id]
        else:
            title = extract_chapter_title(content, f"Chapter {chapter_order + 1}")
        
        chapters.append(Chapter(
            title=title,
            content=text,
            order=chapter_order
        ))
        chapter_order += 1
    
    # If no chapters found, treat entire book as one chapter
    if not chapters:
        # Use list join for O(n) performance instead of O(n²) string concatenation
        text_parts = []
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            text_parts.append(clean_html_text(item.get_content()))
        full_text = "\n".join(text_parts)
        
        if full_text.strip():
            chapters.append(Chapter(
                title=title,
                content=full_text,
                order=0
            ))
    
    return ParsedEpub(
        title=title,
        author=author,
        chapters=chapters,
        cover_image=cover_image,
        cover_media_type=cover_media_type
    )


def get_cover_extension(media_type: str) -> str:
    """Get file extension for cover image based on media type."""
    extensions = {
        'image/jpeg': '.jpg',
        'image/jpg': '.jpg', 
        'image/png': '.png',
        'image/gif': '.gif',
        'image/webp': '.webp',
    }
    return extensions.get(media_type, '.jpg')


if __name__ == "__main__":
    # Quick test
    import sys
    if len(sys.argv) > 1:
        epub_path = sys.argv[1]
        parsed = parse_epub_with_chapters(epub_path)
        print(f"Title: {parsed.title}")
        print(f"Author: {parsed.author}")
        print(f"Cover: {'Yes' if parsed.cover_image else 'No'}")
        print(f"Chapters: {len(parsed.chapters)}")
        for ch in parsed.chapters:
            preview = ch.content[:100].replace('\n', ' ')
            print(f"  {ch.order + 1}. {ch.title} ({len(ch.content)} chars): {preview}...")
