"""
Controller for the PhotoRec Cleaner GUI.

This class encapsulates the application logic, separating it from the Toga
UI implementation in `gui.py`. It handles user actions, manages background
tasks, and updates the application state.
"""

from __future__ import annotations

import asyncio
import contextlib
import csv
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from photorec_refinery.file_utils import (
    OperationCancelled,
    clean_folder,
    get_recup_dirs,
    organize_by_type,
)
from photorec_refinery.gui_utils import shorten_path
from photorec_refinery.photorec_refinery import Cleaner

if TYPE_CHECKING:
    from photorec_refinery.app_state import AppState
    from photorec_refinery.gui import PhotoRecCleanerApp


class AppController:
    """Handles application logic for the PhotoRecCleanerApp."""

    def __init__(self, app: PhotoRecCleanerApp, app_state: AppState):
        self.app = app
        self.app_state = app_state
        self.loop = asyncio.get_running_loop()
        self.cleaner: Cleaner | None = None
        self.monitoring_task: asyncio.Task | None = None
        self.polling_task: asyncio.Task | None = None
        self._stop_monitoring = False
        # Coalesce status updates to avoid UI backlog
        self._last_status_msg: str = ""
        self._status_update_scheduled: bool = False

    def set_cleaner(self, path: str):
        """Instantiates the Cleaner for a given directory."""
        self.cleaner = Cleaner(path)

    def start_folder_polling(self):
        """Starts a background task to poll for new folders."""
        if self.polling_task and not self.polling_task.done():
            self.polling_task.cancel()

        self.polling_task = asyncio.create_task(self._poll_for_folders())

    def stop_folder_polling(self):
        """Stops the folder polling task if running."""
        if self.polling_task and not self.polling_task.done():
            self.polling_task.cancel()

    async def _poll_for_folders(self):
        """Periodically checks for recup_dir folders to enable the Process button."""
        base_dir = self.app.dir_path_input.value
        if not base_dir:
            return

        while True:
            # Only poll if monitoring is NOT active
            if not self.monitoring_task or self.monitoring_task.done():
                recup_dirs = await asyncio.to_thread(get_recup_dirs, base_dir)
                self.app.process_button.enabled = bool(recup_dirs)
            await asyncio.sleep(2)  # Poll every 2 seconds

    def start_monitoring(self):
        """Starts the background monitoring task."""
        self.app_state.cancelled = False
        if self.monitoring_task and not self.monitoring_task.done():
            return  # Already running

        self._stop_monitoring = False
        # Stop the folder poller if it's running, as monitoring takes over.
        if self.polling_task and not self.polling_task.done():
            self.polling_task.cancel()

        self._setup_logging()
        self.monitoring_task = asyncio.create_task(self._monitor_loop())

    def _setup_logging(self):
        """Creates and opens the log file if logging is enabled."""
        if self.app.log_switch.value and self.app.log_path_input.value:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_filename = f"photorec_refinery_log_{ts}.csv"
            log_filepath = Path(self.app.log_path_input.value) / log_filename
            try:
                # The file handle needs to be kept open.
                self.app_state.log_file_handle = log_filepath.open("w", newline="")
                self.app_state.log_writer = csv.writer(self.app_state.log_file_handle)
                self.app_state.log_writer.writerow(
                    ["Folder", "Filename", "Extension", "Status", "Size"]
                )
            except OSError as e:
                self.app.status_label.text = f"Error creating log file: {e}"

    async def _monitor_loop(self):
        """The core loop for repeated scanning and cleaning."""
        try:
            while not self._stop_monitoring:
                if not self.cleaner:
                    self.app.status_label.text = "No directory selected"
                    await asyncio.sleep(1)
                    continue

                # Check for folders. If none, set status and wait.
                recup_dirs = await asyncio.to_thread(
                    get_recup_dirs, self.cleaner.base_dir
                )
                if not recup_dirs:
                    self.app.status_label.text = "Monitoring..."
                    self.app.update_tally()
                    await asyncio.sleep(1)
                    continue

                if self.app.status_label.text == "Monitoring...":
                    self.app.status_label.text = "Processing..."

                # Pass empty strings for extensions if cleaning is disabled
                keep_csv = (
                    self.app.keep_ext_input.value
                    if self.app.cleaning_switch.value
                    else ""
                )
                exclude_csv = (
                    self.app.exclude_ext_input.value
                    if self.app.cleaning_switch.value
                    else ""
                )

                # run_once will now handle both processing completed folders and
                # scanning the active one. The logger callbacks within it are the
                # source of truth for the status label.
                await asyncio.to_thread(
                    self.cleaner.run_once,
                    keep_csv,
                    exclude_csv,
                    self.app_state,
                    self._logger_callback,
                )

                self.app.update_tally()
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            self.app.status_label.text = "Monitoring stopped."
        finally:
            self.monitoring_task = None
            self.start_folder_polling()  # Restart polling when monitoring stops

    async def finish_processing(self):
        """Stops monitoring and performs final cleanup and reorganization."""
        if self.monitoring_task and not self.monitoring_task.done():
            self._stop_monitoring = True
            self.monitoring_task.cancel()

        base_dir = self.app.dir_path_input.value
        if not base_dir:
            return

        loop = asyncio.get_running_loop()
        await asyncio.to_thread(self._finish_processing_sync, base_dir, loop)

    def _finish_processing_sync(self, base_dir: str, loop: asyncio.AbstractEventLoop):
        """Synchronous method for final cleanup and reorganization."""
        if self.app_state.cancelled:
            return

        total_steps = 1  # for closing log file
        if self.app.reorg_switch.value:
            total_steps += 1

        recup_dirs = get_recup_dirs(base_dir)
        if recup_dirs:
            last_folder = recup_dirs[-1]
            if last_folder not in self.app_state.cleaned_folders:
                total_steps += 1

        # Initial progress
        self.loop.call_soon_threadsafe(self.app.update_progress, 0, total_steps)

        steps_done = 0

        if recup_dirs:
            if self.app_state.cancelled:
                return
            last_folder = recup_dirs[-1]
            if last_folder not in self.app_state.cleaned_folders:
                message = f"Processing final folder {shorten_path(last_folder, 60)}..."
                self.loop.call_soon_threadsafe(
                    self.app._set_status_text_threadsafe, message
                )
                # Respect the cleaning switch for the final pass
                keep_ext_str = (
                    self.app.keep_ext_input.value
                    if self.app.cleaning_switch.value
                    else ""
                )
                exclude_ext_str = (
                    self.app.exclude_ext_input.value
                    if self.app.cleaning_switch.value
                    else ""
                )
                keep_ext = {
                    ext.strip() for ext in keep_ext_str.split(",") if ext.strip()
                }
                exclude_ext = {
                    ext.strip() for ext in exclude_ext_str.split(",") if ext.strip()
                }
                try:
                    clean_folder(
                        last_folder,
                        self.app_state,
                        keep_ext=keep_ext,
                        exclude_ext=exclude_ext,
                        logger=self._logger_callback,
                    )
                except OperationCancelled:
                    return
                self.app_state.cleaned_folders.add(last_folder)
                self.loop.call_soon_threadsafe(self.app.update_tally)
                steps_done += 1
                self.loop.call_soon_threadsafe(
                    self.app.update_progress, steps_done, total_steps
                )

        if self.app.reorg_switch.value:
            if self.app_state.cancelled:
                return
            message = "Reorganizing files..."
            self.loop.call_soon_threadsafe(self.app._set_status_text_threadsafe, message)
            batch_size = int(self.app.batch_size_input.value)
            try:
                organize_by_type(base_dir, self.app_state, batch_size=batch_size)
            except OperationCancelled:
                return
            message = "Reorganization complete."
            self.loop.call_soon_threadsafe(
                self.app._set_status_text_threadsafe, message
            )
            steps_done += 1
            self.loop.call_soon_threadsafe(
                self.app.update_progress, steps_done, total_steps
            )

        if self.app_state.cancelled:
            return

        # Write a summary CSV of the final results
        try:
            self._write_summary_csv(base_dir)
        except OSError:
            # Ignore write errors; UI already shows the summary dialog
            pass

        self._close_log_file()
        steps_done += 1
        self.loop.call_soon_threadsafe(self.app.update_progress, steps_done, total_steps)

    def _close_log_file(self) -> None:
        """Closes the log file handle if it's open."""
        handle = self.app_state.log_file_handle
        if handle is None:
            self.app_state.log_writer = None
            self.app_state.log_file_handle = None
            return
        try:
            if not handle.closed:
                with contextlib.suppress(Exception):
                    handle.flush()
                handle.close()
        except Exception:
            # Best-effort close; ignore races from concurrent cancellation
            pass
        finally:
            self.app_state.log_writer = None
            self.app_state.log_file_handle = None

    async def perform_one_shot_clean(self):
        """Runs the cleaning process once for all existing folders."""
        self.app_state.reset()  # Reset state before starting a new operation
        base_dir = self.app.dir_path_input.value
        if not base_dir:
            return

        loop = asyncio.get_running_loop()
        await asyncio.to_thread(self._one_shot_clean_sync, base_dir, loop)

    def _one_shot_clean_sync(self, base_dir: str, loop: asyncio.AbstractEventLoop):
        """Synchronous method to clean all existing folders."""
        asyncio.run_coroutine_threadsafe(self.app._update_tally_async(), loop)

        self._setup_logging()

        recup_dirs = get_recup_dirs(base_dir)
        if not recup_dirs:
            message = "No 'recup_dir' folders found to clean."
            asyncio.run_coroutine_threadsafe(
                self.app._set_status_text_async(message), loop
            )
            return

        num_folders = len(recup_dirs)
        self.loop.call_soon_threadsafe(self.app.update_progress, 0, num_folders)

        # Respect the cleaning switch for the one-shot process
        keep_ext_str = (
            self.app.keep_ext_input.value if self.app.cleaning_switch.value else ""
        )
        exclude_ext_str = (
            self.app.exclude_ext_input.value if self.app.cleaning_switch.value else ""
        )
        keep_ext = {ext.strip() for ext in keep_ext_str.split(",") if ext.strip()}
        exclude_ext = {ext.strip() for ext in exclude_ext_str.split(",") if ext.strip()}

        for i, folder in enumerate(recup_dirs):
            if self.app_state.cancelled:
                break
            message = f"Processing folder {i + 1}/{num_folders}..."
            self.loop.call_soon_threadsafe(
                self.app._set_status_text_threadsafe, message
            )
            try:
                clean_folder(
                    folder,
                    self.app_state,
                    keep_ext=keep_ext,
                    exclude_ext=exclude_ext,
                    logger=self._logger_callback,
                    prefix="Processing",
                )
            except OperationCancelled:
                break
            self.app_state.cleaned_folders.add(folder)
            self.loop.call_soon_threadsafe(self.app.update_tally)
            self.loop.call_soon_threadsafe(
                self.app.update_progress, i + 1, num_folders
            )

        if self.app_state.cancelled:
            self._close_log_file()
            return

        if self.app.reorg_switch.value:
            message = "Reorganizing files..."
            self.loop.call_soon_threadsafe(
                self.app._set_status_text_threadsafe, message
            )
            batch_size = int(self.app.batch_size_input.value)
            with contextlib.suppress(OperationCancelled):
                organize_by_type(base_dir, self.app_state, batch_size=batch_size)
            message = "Reorganization complete."
            self.loop.call_soon_threadsafe(
                self.app._set_status_text_threadsafe, message
            )

        if self.app_state.cancelled:
            self._close_log_file()
            return

        report = (
            f"One-Shot Processing Complete\n\n"
            f"Folders Processed: {len(self.app_state.cleaned_folders)}\n"
            f"Files Kept: {self.app_state.total_kept_count}\n"
            f"Files Deleted: {self.app_state.total_deleted_count}\n"
            f"Total Space Saved: {self.app._format_size(self.app_state.total_deleted_size)}"
        )
        asyncio.run_coroutine_threadsafe(
            self.app._show_dialog_async("Processing Complete", report),
            loop,
        )
        # Write a summary CSV of the final results
        with contextlib.suppress(OSError):
            self._write_summary_csv(base_dir)

        self._close_log_file()

    def on_close(self):
        """Handles app shutdown."""
        self.app_state.cancelled = True  # Signal cancellation on close
        if self.monitoring_task and not self.monitoring_task.done():
            self.monitoring_task.cancel()

        if self.polling_task and not self.polling_task.done():
            self.polling_task.cancel()

        self._close_log_file()

    def cancel(self):
        """Immediately stops all processing."""
        self.app_state.cancelled = True
        if self.monitoring_task and not self.monitoring_task.done():
            self._stop_monitoring = True
            self.monitoring_task.cancel()

        if self.polling_task and not self.polling_task.done():
            self.polling_task.cancel()

        # Close log file immediately so no further writes occur
        self._close_log_file()

        self.app.status_label.text = "Processing cancelled."

    def _logger_callback(self, message: str):
        """Callback from worker threads to update UI; coalesces messages."""
        if (
            not message
            or self.app_state.cancelled
            or getattr(self.app, "drop_updates", False)
        ):
            return

        # Ignore noisy per-file messages; keep high-level progress only
        if message.startswith("Kept:") or message.startswith("Deleted:"):
            return

        # Coalesce to the latest message and schedule a single UI update
        self._last_status_msg = message
        if not self._status_update_scheduled:
            self._status_update_scheduled = True
            self.loop.call_soon_threadsafe(self._flush_status_update)

    def _flush_status_update(self) -> None:
        """Runs on the event loop to apply the latest status update once."""
        try:
            if not self.app_state.cancelled and not getattr(
                self.app, "drop_updates", False
            ):
                self.app.update_status(self._last_status_msg)
        finally:
            self._status_update_scheduled = False

    # --- Summary CSV writing ---
    def _write_summary_csv(self, base_dir: str) -> None:
        """Writes a compact CSV with final summary metrics.

        Saves to the log folder if logging is enabled; otherwise to the
        selected PhotoRec directory.
        """
        # Decide output directory
        if self.app.log_switch.value and self.app.log_path_input.value:
            out_dir = Path(self.app.log_path_input.value)
        else:
            out_dir = Path(base_dir)

        out_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        outfile = out_dir / f"photorec_refinery_summary_{ts}.csv"

        # Prepare a single-row CSV with fixed columns
        headers = [
            "timestamp",
            "base_dir",
            "folders_processed",
            "files_kept",
            "files_deleted",
            "total_space_saved_bytes",
            "total_space_saved_gb",
        ]
        gb = self.app_state.total_deleted_size / (1024 ** 3) if self.app_state.total_deleted_size else 0.0
        row = [
            ts,
            str(base_dir),
            len(self.app_state.cleaned_folders),
            self.app_state.total_kept_count,
            self.app_state.total_deleted_count,
            self.app_state.total_deleted_size,
            f"{gb:.3f}",
        ]

        with outfile.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerow(row)
