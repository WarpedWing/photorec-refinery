"""
Cleaner core logic. Exposes a Cleaner class with a run_once() method
that performs one pass of scanning/cleaning. This keeps the long-running
work out of the event loop; gui.py will call run_once via asyncio.to_thread.


This module deliberately keeps side effects minimal: it returns structured
results rather than mutating UI objects directly.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

from .file_utils import clean_folder, get_recup_dirs, OperationCancelled

if TYPE_CHECKING:
    from collections.abc import Callable

    from .app_state import AppState


class CleanerResult(TypedDict):
    """Return type for Cleaner.run_once()"""

    processed_folders: list[str]
    last_deleted: None
    cleaned_count: int
    timestamp: float


class Cleaner:
    def __init__(self, base_dir: str):
        self.base_dir = base_dir

    def _normalize_ext_set(self, ext_csv: str) -> set[str]:
        return {e.strip().lower() for e in ext_csv.split(",") if e.strip()}

    def run_once(
        self,
        keep_ext_csv: str,
        exclude_ext_csv: str,
        app_state: AppState,
        logger: Callable[[str], None] | None = None,
    ) -> CleanerResult:
        keep_ext = self._normalize_ext_set(keep_ext_csv)
        exclude_ext = self._normalize_ext_set(exclude_ext_csv)

        processed = []

        recup_dirs = get_recup_dirs(self.base_dir)
        if not recup_dirs:
            return {
                "processed_folders": [],
                "last_deleted": None,
                "cleaned_count": 0,
                "timestamp": time.time(),
            }

        active_folder = recup_dirs[-1]
        folders_to_process = [
            d
            for d in recup_dirs
            if d not in app_state.cleaned_folders and d != active_folder
        ]

        # Process fully completed folders (safe to clean/delete)
        for folder in folders_to_process:
            if app_state.cancelled:
                raise OperationCancelled()
            if logger:
                logger(f"Processing {folder}")
            # perform actual cleaning -> this updates app_state counters
            try:
                clean_folder(
                    folder,
                    app_state,
                    keep_ext=keep_ext,
                    exclude_ext=exclude_ext,
                    logger=logger,
                    prefix="Processing",
                )
            except OperationCancelled:
                raise
            # mark it as cleaned so we don't reprocess
            app_state.cleaned_folders.add(folder)
            processed.append(folder)

        # For live feedback, simply log the name of the active folder.
        # The controller loop handles the "Monitoring..." status if no folders exist.
        if active_folder and logger and not app_state.cancelled:
            logger(f"Processing folder: {Path(active_folder).name}")

        return {
            "processed_folders": processed,
            "last_deleted": None,
            "cleaned_count": len(processed),
            "timestamp": time.time(),
        }
