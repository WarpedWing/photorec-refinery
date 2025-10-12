"""
Application state container for PhotoRec Cleaner.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import IO, Any


@dataclass
class AppState:
    """Holds counters and shared state between GUI and cleaner."""

    cleaned_folders: set[str] = field(default_factory=set)
    kept_files: dict[str, list[str]] = field(default_factory=dict)
    total_kept_count: int = 0
    total_deleted_count: int = 0
    total_deleted_size: int = 0
    log_writer: Any = None  # csv.writer instance
    log_file_handle: IO[str] | None = None
    cancelled: bool = False

    # Console UI specific attributes (may not be present in GUI mode)
    current_activity: str = ""
    spinner_index: int = 0
    app_state: str = "idle"
    final_cleanup: bool = False
    ready_for_final_cleanup: bool = False

    def reset(self) -> None:
        """Resets all counters and state to their initial values."""
        self.cleaned_folders.clear()
        self.kept_files.clear()
        self.total_kept_count = 0
        self.total_deleted_count = 0
        self.total_deleted_size = 0
        self.log_writer = None
        if self.log_file_handle is not None:
            self.log_file_handle.close()
            self.log_file_handle = None
        self.cancelled = False
