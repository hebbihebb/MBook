"""
Progress Manager for Maya1 Audiobook Converter

Handles saving/loading conversion progress for crash-resume capability.
Progress is saved after each chunk completes, allowing resumption from
the last successful chunk if the app crashes or is closed.
"""

import json
import os
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from datetime import datetime


@dataclass
class ConversionProgress:
    """State of an in-progress conversion."""
    epub_path: str
    output_dir: str
    selected_chapters: List[int]  # Indices of chapters to convert
    voice_prompt: str
    total_chunks: int
    completed_chunks: List[int] = field(default_factory=list)  # Indices of completed chunks
    chunk_files: Dict[int, str] = field(default_factory=dict)  # chunk_idx -> temp wav path
    chunk_to_chapter: List[int] = field(default_factory=list)  # Maps chunk idx -> chapter idx
    chapter_titles: List[str] = field(default_factory=list)
    started_at: str = ""
    last_updated: str = ""
    
    def __post_init__(self):
        if not self.started_at:
            self.started_at = datetime.now().isoformat()
        self.last_updated = datetime.now().isoformat()


def get_progress_file_path(output_dir: str) -> str:
    """Get the path to the progress file for a given output directory."""
    return os.path.join(output_dir, ".conversion_progress.json")


def save_progress(output_dir: str, progress: ConversionProgress) -> str:
    """
    Save conversion progress to JSON file.
    
    Args:
        output_dir: Directory containing the conversion output
        progress: Current conversion state
        
    Returns:
        Path to the saved progress file
    """
    progress.last_updated = datetime.now().isoformat()
    progress_file = get_progress_file_path(output_dir)
    
    # Convert dataclass to dict, handling the Dict[int, str] type
    data = asdict(progress)
    # JSON requires string keys, so convert int keys to strings
    data['chunk_files'] = {str(k): v for k, v in progress.chunk_files.items()}
    
    with open(progress_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    
    return progress_file


def load_progress(output_dir: str) -> Optional[ConversionProgress]:
    """
    Load conversion progress from JSON file.
    
    Args:
        output_dir: Directory containing the conversion output
        
    Returns:
        ConversionProgress if file exists and is valid, None otherwise
    """
    progress_file = get_progress_file_path(output_dir)
    
    if not os.path.exists(progress_file):
        return None
    
    try:
        with open(progress_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Convert string keys back to int for chunk_files
        if 'chunk_files' in data:
            data['chunk_files'] = {int(k): v for k, v in data['chunk_files'].items()}
        
        return ConversionProgress(**data)
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        print(f"Warning: Failed to load progress file: {e}")
        return None


def has_resumable_job(epub_path: str, output_dir: str) -> bool:
    """
    Check if there's a resumable job for the given EPUB and output dir.
    
    Args:
        epub_path: Path to the EPUB file
        output_dir: Output directory
        
    Returns:
        True if a resumable job exists for this EPUB
    """
    progress = load_progress(output_dir)
    if progress is None:
        return False
    
    # Verify it's the same EPUB
    if os.path.normpath(progress.epub_path) != os.path.normpath(epub_path):
        return False
    
    # Verify there are incomplete chunks
    if len(progress.completed_chunks) >= progress.total_chunks:
        return False
    
    # Verify at least some chunk files still exist
    existing_chunks = sum(
        1 for path in progress.chunk_files.values() 
        if os.path.exists(path)
    )
    
    return existing_chunks > 0


def get_resumable_info(output_dir: str) -> Optional[Dict]:
    """
    Get summary info about a resumable job.
    
    Args:
        output_dir: Output directory to check
        
    Returns:
        Dict with 'completed', 'total', 'epub_path', 'started_at' or None
    """
    progress = load_progress(output_dir)
    if progress is None:
        return None
    
    # Count existing chunk files
    existing_chunks = [
        idx for idx, path in progress.chunk_files.items()
        if os.path.exists(path)
    ]
    
    return {
        'completed': len(existing_chunks),
        'total': progress.total_chunks,
        'epub_path': progress.epub_path,
        'started_at': progress.started_at,
        'selected_chapters': progress.selected_chapters,
        'voice_prompt': progress.voice_prompt
    }


def cleanup_progress(output_dir: str) -> None:
    """
    Delete progress file after successful completion.
    
    Args:
        output_dir: Directory containing the progress file
    """
    progress_file = get_progress_file_path(output_dir)
    if os.path.exists(progress_file):
        try:
            os.remove(progress_file)
        except OSError as e:
            print(f"Warning: Failed to delete progress file: {e}")


def cleanup_temp_chunks(output_dir: str) -> None:
    """
    Delete temporary chunk files from a failed/cancelled conversion.
    
    Args:
        output_dir: Directory containing the conversion output
    """
    progress = load_progress(output_dir)
    if progress is None:
        return
    
    for chunk_path in progress.chunk_files.values():
        if os.path.exists(chunk_path):
            try:
                os.remove(chunk_path)
            except OSError:
                pass
    
    # Also try to remove temp_chunks directory
    temp_dir = os.path.join(output_dir, "temp_chunks")
    if os.path.exists(temp_dir):
        try:
            os.rmdir(temp_dir)  # Only removes if empty
        except OSError:
            pass
    
    cleanup_progress(output_dir)
