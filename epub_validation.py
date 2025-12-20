"""
EPUB Validation Module

This module provides security checks for EPUB files (which are ZIP archives)
to prevent ZIP bomb attacks and other malformed file issues.
"""

import zipfile
import os
import logging

# Security Constants
MAX_UNCOMPRESSED_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB
MAX_FILE_COUNT = 100000  # 100k files seems plenty for an ebook
MAX_SINGLE_FILE_SIZE = 500 * 1024 * 1024  # 500 MB for a single file

logger = logging.getLogger(__name__)

def validate_epub_safe(epub_path: str,
                      max_uncompressed_size: int = MAX_UNCOMPRESSED_SIZE,
                      max_file_count: int = MAX_FILE_COUNT) -> bool:
    """
    Validates an EPUB (ZIP) file to prevent ZIP bomb attacks.

    Args:
        epub_path: Path to the EPUB file.
        max_uncompressed_size: Maximum allowed total uncompressed size in bytes.
        max_file_count: Maximum allowed number of files in the archive.

    Returns:
        True if the file passes validation.

    Raises:
        ValueError: If the file is unsafe or invalid.
        FileNotFoundError: If the file does not exist.
    """
    if not os.path.exists(epub_path):
        raise FileNotFoundError(f"File not found: {epub_path}")

    # Basic check if it is a zip file
    if not zipfile.is_zipfile(epub_path):
        raise ValueError("File is not a valid ZIP/EPUB archive")

    try:
        with zipfile.ZipFile(epub_path, 'r') as zf:
            total_uncompressed_size = 0
            file_count = 0

            for info in zf.infolist():
                file_count += 1
                if file_count > max_file_count:
                    raise ValueError(f"Too many files in EPUB (>{max_file_count})")

                # ZipInfo.file_size is the uncompressed size
                if info.file_size > MAX_SINGLE_FILE_SIZE:
                    raise ValueError(f"Single file '{info.filename}' exceeds size limit ({MAX_SINGLE_FILE_SIZE} bytes)")

                total_uncompressed_size += info.file_size
                if total_uncompressed_size > max_uncompressed_size:
                    raise ValueError(f"Total uncompressed size exceeds limit ({max_uncompressed_size} bytes)")

                # Check for suspicious compression ratios on large files (e.g. 100MB+ expanding 1000x)
                # But rely mainly on total size limit.

    except zipfile.BadZipFile:
        raise ValueError("Invalid EPUB file (bad zip structure)")
    except Exception as e:
        # Re-raise known errors, wrap others
        if isinstance(e, ValueError):
            raise
        raise ValueError(f"Error validating EPUB: {str(e)}")

    logger.debug(f"EPUB validation passed: {file_count} files, {total_uncompressed_size/1024/1024:.2f} MB total")
    return True
