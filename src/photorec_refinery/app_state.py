"""
Application state container for PhotoRec Cleaner.
"""
from dataclasses import dataclass, field
from typing import Any, Union


@dataclass
class AppState:
    """Holds counters and shared state between GUI and cleaner."""

    cleaned_folders: set = field(default_factory=set)
    kept_files: dict = field(default_factory=dict)
    total_kept_count: int = 0
    total_deleted_count: int = 0
    total_deleted_size: int = 0
    log_writer: Union[Any, None] = None
    log_file_handle: Union[Any, None] = None
    cancelled: bool = False

    def reset(self):
        """Resets all counters and state to their initial values."""
        self.cleaned_folders.clear()
        self.kept_files.clear()
        self.total_kept_count = 0
        self.total_deleted_count = 0
        self.total_deleted_size = 0
        self.log_writer = None
        if getattr(self, "log_file_handle", None):
            self.log_file_handle.close()
            self.log_file_handle = None
        self.cancelled = False
