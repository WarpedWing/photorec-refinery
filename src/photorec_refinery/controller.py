"""
Controller for the PhotoRec Cleaner GUI.

This class encapsulates the application logic, separating it from the Toga
UI implementation in `gui.py`. It handles user actions, manages background
tasks, and updates the application state.
"""

from __future__ import annotations

import asyncio
import csv
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from photorec_refinery.file_utils import (
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

    def set_cleaner(self, path: str):
        """Instantiates the Cleaner for a given directory."""
        self.cleaner = Cleaner(path)

    def start_folder_polling(self):
        """Starts a background task to poll for new folders."""
        if self.polling_task and not self.polling_task.done():
            self.polling_task.cancel()

        self.polling_task = asyncio.create_task(self._poll_for_folders())

    async def _poll_for_folders(self):
        """Periodically checks for recup_dir folders to enable the Process Now button."""
        base_dir = self.app.dir_path_input.value
        if not base_dir:
            return

        while True:
            # Only poll if monitoring is NOT active
            if not self.monitoring_task or self.monitoring_task.done():
                recup_dirs = await asyncio.to_thread(get_recup_dirs, base_dir)
                self.app.clean_now_button.enabled = bool(recup_dirs)
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

        asyncio.run_coroutine_threadsafe(
            self.app._update_progress_async(0, total_steps), loop
        )

        steps_done = 0

        if recup_dirs:
            if self.app_state.cancelled:
                return
            last_folder = recup_dirs[-1]
            if last_folder not in self.app_state.cleaned_folders:
                message = f"Processing final folder {shorten_path(last_folder, 60)}..."
                asyncio.run_coroutine_threadsafe(
                    self.app._set_status_text_async(message), loop
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
                clean_folder(
                    last_folder,
                    self.app_state,
                    keep_ext=keep_ext,
                    exclude_ext=exclude_ext,
                    logger=self._logger_callback,
                )
                self.app_state.cleaned_folders.add(last_folder)
                asyncio.run_coroutine_threadsafe(self.app._update_tally_async(), loop)
                steps_done += 1
                asyncio.run_coroutine_threadsafe(
                    self.app._update_progress_async(steps_done, total_steps), loop
                )

        if self.app.reorg_switch.value:
            if self.app_state.cancelled:
                return
            message = "Reorganizing files..."
            asyncio.run_coroutine_threadsafe(
                self.app._set_status_text_async(message), loop
            )
            batch_size = int(self.app.batch_size_input.value)
            organize_by_type(base_dir, self.app_state, batch_size=batch_size)
            message = "Reorganization complete."
            asyncio.run_coroutine_threadsafe(
                self.app._set_status_text_async(message), loop
            )
            steps_done += 1
            asyncio.run_coroutine_threadsafe(
                self.app._update_progress_async(steps_done, total_steps), loop
            )

        if self.app_state.cancelled:
            return

        self._close_log_file()
        steps_done += 1
        asyncio.run_coroutine_threadsafe(
            self.app._update_progress_async(steps_done, total_steps), loop
        )

    def _close_log_file(self) -> None:
        """Closes the log file handle if it's open."""
        if self.app_state.log_file_handle is not None:
            self.app_state.log_file_handle.close()
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
        asyncio.run_coroutine_threadsafe(
            self.app._update_progress_async(0, num_folders), loop
        )

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
            asyncio.run_coroutine_threadsafe(
                self.app._set_status_text_async(message), loop
            )
            clean_folder(
                folder,
                self.app_state,
                keep_ext=keep_ext,
                exclude_ext=exclude_ext,
                logger=self._logger_callback,
                prefix="Processing",
            )
            self.app_state.cleaned_folders.add(folder)
            asyncio.run_coroutine_threadsafe(self.app._update_tally_async(), loop)
            asyncio.run_coroutine_threadsafe(
                self.app._update_progress_async(i + 1, num_folders), loop
            )

        if self.app_state.cancelled:
            self._close_log_file()
            return

        if self.app.reorg_switch.value:
            message = "Reorganizing files..."
            asyncio.run_coroutine_threadsafe(
                self.app._set_status_text_async(message), loop
            )
            batch_size = int(self.app.batch_size_input.value)
            organize_by_type(base_dir, self.app_state, batch_size=batch_size)
            message = "Reorganization complete."
            asyncio.run_coroutine_threadsafe(
                self.app._set_status_text_async(message), loop
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

        self.app.status_label.text = "Processing cancelled."

    def _logger_callback(self, message: str):
        """Callback from background threads to update UI with status."""
        if not message:
            return

        # Pass all messages to the status label
        self.loop.call_soon_threadsafe(self.app.update_status, message)
