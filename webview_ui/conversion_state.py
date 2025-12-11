"""
Conversion State Management for WebUI

Thread-safe state management for audiobook conversion jobs.
Provides a central state object that can be updated by the worker thread
and read by Flask request handlers.
"""

from dataclasses import dataclass, field
from collections import deque
from typing import Optional, Deque, Dict
from datetime import datetime
import threading


@dataclass
class ConversionState:
    """Global state for the current conversion job."""
    job_id: str
    status: str  # "idle", "running", "paused", "cancelled", "completed", "error"
    progress: float  # 0-100
    current_chunk: int
    total_chunks: int
    current_status_text: str
    log_messages: Deque[Dict] = field(default_factory=lambda: deque(maxlen=100))
    error_message: Optional[str] = None
    final_path: Optional[str] = None

    # Control signals
    cancel_event: threading.Event = field(default_factory=threading.Event)
    pause_event: threading.Event = field(default_factory=threading.Event)

    # Thread safety
    lock: threading.Lock = field(default_factory=threading.Lock)

    def add_log(self, message: str, level: str = "info"):
        """
        Thread-safe log message addition.

        Args:
            message: Log message text
            level: Log level ("info", "warning", "error", "success")
        """
        with self.lock:
            self.log_messages.append({
                "level": level,
                "message": message,
                "timestamp": datetime.now().isoformat()
            })

    def update_progress(self, progress: float, status_text: str = None):
        """
        Thread-safe progress update.

        Args:
            progress: Progress percentage (0-100)
            status_text: Optional status text to update
        """
        with self.lock:
            self.progress = min(100.0, max(0.0, progress))
            if status_text:
                self.current_status_text = status_text

    def set_status(self, status: str):
        """
        Thread-safe status update.

        Args:
            status: New status ("running", "paused", "cancelled", "completed", "error")
        """
        with self.lock:
            self.status = status

    def set_error(self, error_message: str):
        """
        Thread-safe error state update.

        Args:
            error_message: Error message to set
        """
        with self.lock:
            self.status = "error"
            self.error_message = error_message
            self.add_log(f"Fatal error: {error_message}", "error")

    def set_completed(self, final_path: str):
        """
        Thread-safe completion state update.

        Args:
            final_path: Path to the final audiobook file
        """
        with self.lock:
            self.status = "completed"
            self.progress = 100.0
            self.final_path = final_path
