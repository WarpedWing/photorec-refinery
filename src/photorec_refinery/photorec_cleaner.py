"""
Cleaner core logic. Exposes a Cleaner class with a run_once() method
that performs one pass of scanning/cleaning. This keeps the long-running
work out of the event loop; gui.py will call run_once via asyncio.to_thread.


This module deliberately keeps side effects minimal: it returns structured
results rather than mutating UI objects directly.
"""

import os
import time
from typing import Dict,  Optional

from .app_state import AppState
from .file_utils import clean_folder, get_recup_dirs


class Cleaner:
    def __init__(self, base_dir: str):
        self.base_dir = base_dir

    def _normalize_ext_set(self, ext_csv: str) -> set:
        return {e.strip().lower() for e in ext_csv.split(",") if e.strip()}

    def run_once(
        self,
        keep_ext_csv: str,
        exclude_ext_csv: str,
        app_state: AppState,
        logger: Optional[callable] = None,
    ) -> Dict:
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
            if logger:
                logger(f"Processing {folder}")
            # perform actual cleaning -> this updates app_state counters
            clean_folder(
                folder,
                app_state,
                keep_ext=keep_ext,
                exclude_ext=exclude_ext,
                logger=logger,
                prefix="Processing",
            )
            # mark it as cleaned so we don't reprocess
            app_state.cleaned_folders.add(folder)
            processed.append(folder)

        # For live feedback, simply log the name of the active folder.
        # The controller loop handles the "Monitoring..." status if no folders exist.
        if active_folder:
            if logger:
                logger(f"Processing folder: {os.path.basename(active_folder)}")

        return {
            "processed_folders": processed,
            "last_deleted": None,
            "cleaned_count": len(processed),
            "timestamp": time.time(),
        }
