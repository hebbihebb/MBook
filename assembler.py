import os
import re
from pydub import AudioSegment
import subprocess
from typing import List, Dict, Optional


def sanitize_metadata(value: str) -> str:
    """
    Sanitizes metadata values to prevent command injection in ffmpeg calls.

    Removes or escapes characters that could be used for command injection:
    - Newlines, carriage returns, tabs
    - Shell metacharacters: ; | & $ ` \ " ' < >
    - Control characters

    Args:
        value: The metadata value to sanitize

    Returns:
        Sanitized metadata value safe for ffmpeg
    """
    if not isinstance(value, str):
        value = str(value)

    # Remove control characters and newlines
    value = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', value)

    # Remove potentially dangerous shell metacharacters
    dangerous_chars = [';', '|', '&', '$', '`', '\\', '"', "'", '<', '>', '\n', '\r', '\t']
    for char in dangerous_chars:
        value = value.replace(char, '')

    # Limit length to prevent extremely long metadata
    max_length = 500
    if len(value) > max_length:
        value = value[:max_length]

    return value.strip()


def stitch_audio(audio_chunks: List[str], output_path: str = "temp_book.wav") -> str:
    """
    Stitches audio chunks with exactly 400ms of silence between them.
    
    Args:
        audio_chunks: List of paths to audio files.
        output_path: Path for the output WAV file.
        
    Returns:
        Path to the stitched audio file.
    """
    combined = AudioSegment.empty()
    silence_400ms = AudioSegment.silent(duration=400)

    for i, chunk in enumerate(audio_chunks):
        if isinstance(chunk, str):
            segment = AudioSegment.from_file(chunk)
        else:
            segment = chunk
        
        combined += segment
        
        # Add silence between chunks, but not after the last one
        if i < len(audio_chunks) - 1:
            combined += silence_400ms

    combined.export(output_path, format="wav")
    return output_path


def stitch_audio_with_chapter_tracking(
    audio_chunks: List[str],
    chunk_to_chapter: List[int],
    chapter_titles: List[str],
    output_path: str = "temp_book.wav"
) -> tuple[str, List[Dict]]:
    """
    Stitches audio chunks and tracks chapter boundaries.
    
    Args:
        audio_chunks: List of paths to audio files.
        chunk_to_chapter: List mapping each chunk index to its chapter index.
        chapter_titles: List of chapter titles.
        output_path: Path for the output WAV file.
        
    Returns:
        Tuple of (output_path, chapters_info) where chapters_info is a list of
        dicts with 'title', 'start_ms', 'end_ms'.
    """
    combined = AudioSegment.empty()
    silence_400ms = AudioSegment.silent(duration=400)
    
    # Track chapter boundaries
    chapter_starts = {}  # chapter_index -> start_ms
    current_position_ms = 0
    
    for i, chunk_path in enumerate(audio_chunks):
        chapter_idx = chunk_to_chapter[i]
        
        # Record start of chapter if this is the first chunk of a new chapter
        if chapter_idx not in chapter_starts:
            chapter_starts[chapter_idx] = current_position_ms
        
        # Load and append audio
        segment = AudioSegment.from_file(chunk_path)
        combined += segment
        current_position_ms += len(segment)
        
        # Add silence between chunks, but not after the last one
        if i < len(audio_chunks) - 1:
            combined += silence_400ms
            current_position_ms += 400
    
    # Export the combined audio
    combined.export(output_path, format="wav")
    
    # Build chapter info with end times
    total_duration_ms = current_position_ms
    chapter_indices = sorted(chapter_starts.keys())
    
    chapters_info = []
    for i, chapter_idx in enumerate(chapter_indices):
        start_ms = chapter_starts[chapter_idx]
        
        # End time is start of next chapter, or total duration for last chapter
        if i + 1 < len(chapter_indices):
            end_ms = chapter_starts[chapter_indices[i + 1]]
        else:
            end_ms = total_duration_ms
        
        title = chapter_titles[chapter_idx] if chapter_idx < len(chapter_titles) else f"Chapter {chapter_idx + 1}"
        
        chapters_info.append({
            'title': title,
            'start_ms': start_ms,
            'end_ms': end_ms
        })
    
    return output_path, chapters_info


def generate_chapter_metadata(chapters: List[Dict], output_path: str = "chapters.txt") -> str:
    """
    Generate FFMETADATA file for chapter markers.
    
    Args:
        chapters: List of dicts with 'title', 'start_ms', 'end_ms'.
        output_path: Path for the metadata file.
        
    Returns:
        Path to the metadata file.
    """
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(";FFMETADATA1\n\n")
        
        for ch in chapters:
            f.write("[CHAPTER]\n")
            f.write("TIMEBASE=1/1000\n")
            f.write(f"START={ch['start_ms']}\n")
            f.write(f"END={ch['end_ms']}\n")
            # Escape special characters in title
            title = ch['title'].replace('=', '\\=').replace(';', '\\;').replace('#', '\\#').replace('\\', '\\\\')
            f.write(f"title={title}\n\n")
    
    return output_path


def export_m4b(
    wav_path: str,
    output_m4b_path: str,
    metadata: Optional[Dict] = None,
    cover_art_path: Optional[str] = None,
    chapters_file: Optional[str] = None
) -> str:
    """
    Converts WAV to M4B with metadata and chapter markers using ffmpeg.
    
    Args:
        wav_path: Path to input WAV file.
        output_m4b_path: Path for output M4B file.
        metadata: Dict with 'title', 'author'.
        cover_art_path: Optional path to cover image.
        chapters_file: Optional path to FFMETADATA chapters file.
        
    Returns:
        Path to the M4B file.
    """
    cmd = ["ffmpeg", "-y"]
    
    # Input files
    cmd.extend(["-i", wav_path])
    
    if chapters_file and os.path.exists(chapters_file):
        cmd.extend(["-i", chapters_file])
    
    if cover_art_path and os.path.exists(cover_art_path):
        cmd.extend(["-i", cover_art_path])
    
    # Map streams
    cmd.extend(["-map", "0:a"])  # Audio from first input
    
    if cover_art_path and os.path.exists(cover_art_path):
        # Map cover art as attached picture
        cover_input_idx = 2 if chapters_file else 1
        cmd.extend(["-map", f"{cover_input_idx}:v"])
        cmd.extend(["-c:v", "copy"])
        cmd.extend(["-disposition:v:0", "attached_pic"])
    
    # Import chapter metadata
    if chapters_file and os.path.exists(chapters_file):
        cmd.extend(["-map_metadata", "1"])
    
    # Audio codec settings (standard audiobook settings)
    cmd.extend(["-c:a", "aac", "-b:a", "64k"])
    
    # Book metadata (sanitized to prevent command injection)
    if metadata:
        if "title" in metadata:
            safe_title = sanitize_metadata(metadata['title'])
            cmd.extend(["-metadata", f"title={safe_title}"])
        if "author" in metadata:
            safe_author = sanitize_metadata(metadata['author'])
            cmd.extend(["-metadata", f"artist={safe_author}"])
            cmd.extend(["-metadata", f"album_artist={safe_author}"])
        # Mark as audiobook
        cmd.extend(["-metadata", "genre=Audiobook"])
    
    cmd.append(output_m4b_path)
    
    print(f"Running command: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    
    return output_m4b_path


def create_audiobookshelf_folder(
    output_dir: str,
    author: str,
    title: str,
    m4b_path: str,
    cover_image_bytes: Optional[bytes] = None,
    cover_extension: str = ".jpg"
) -> str:
    """
    Create Audiobookshelf-compatible folder structure.
    
    Structure: {output_dir}/{author}/{title}/{title}.m4b
    
    Args:
        output_dir: Base output directory.
        author: Author name.
        title: Book title.
        m4b_path: Path to the M4B file to move/copy.
        cover_image_bytes: Optional cover image data.
        cover_extension: Extension for cover image (e.g., '.jpg', '.png').
        
    Returns:
        Path to the final M4B file location.
    """
    import shutil
    
    # Sanitize names for filesystem
    def sanitize_name(name: str) -> str:
        # Remove/replace problematic characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, '_')
        return name.strip()
    
    safe_author = sanitize_name(author)
    safe_title = sanitize_name(title)
    
    # Create folder structure
    book_folder = os.path.join(output_dir, safe_author, safe_title)
    os.makedirs(book_folder, exist_ok=True)
    
    # Move/copy M4B file
    final_m4b_path = os.path.join(book_folder, f"{safe_title}.m4b")
    if m4b_path != final_m4b_path:
        shutil.move(m4b_path, final_m4b_path)
    
    # Save cover image if provided
    if cover_image_bytes:
        cover_path = os.path.join(book_folder, f"cover{cover_extension}")
        with open(cover_path, 'wb') as f:
            f.write(cover_image_bytes)
    
    return final_m4b_path
