"""
Toga GUI for PhotoRec Cleaner — rewritten to run the cleaning logic
off-thread, keep the UI responsive, avoid dangling tasks, and provide
concise status updates.

Notes:
 - Uses asyncio.create_task to start the monitor loop.
 - Calls Cleaner.run_once inside asyncio.to_thread to avoid blocking the event loop.
 - Provides two status labels: one for general state and one for the last file (truncated).
 - Graceful shutdown: Finish button cancels the background task and waits briefly for it to stop.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import toga
from toga.constants import GREEN
from toga.style import Pack

from photorec_refinery.app_state import AppState
from photorec_refinery.controller import AppController
from photorec_refinery.file_utils import get_recup_dirs
from photorec_refinery.gui_utils import shorten_path


class PhotoRecCleanerApp(toga.App):
    # Instance attributes type hints
    app_state: AppState
    controller: AppController
    main_box: toga.Box
    dir_path_input: toga.TextInput
    cleaning_switch: toga.Switch
    keep_ext_input: toga.TextInput
    exclude_ext_input: toga.TextInput
    log_switch: toga.Switch
    log_path_input: toga.TextInput
    log_path_button: toga.Button
    reorg_switch: toga.Switch
    batch_size_input: toga.NumberInput
    folders_processed_label: toga.Label
    files_kept_label: toga.Label
    files_deleted_label: toga.Label
    space_saved_label: toga.Label
    progress_bar: toga.ProgressBar
    activity_indicator: toga.ActivityIndicator
    guidance_label: toga.Label
    status_label: toga.Label
    clean_now_button: toga.Button
    start_button: toga.Button
    finish_button: toga.Button
    help_window: toga.Window | None

    def startup(self) -> None:
        self.main_window = toga.MainWindow(
            title=self.formal_name
        )  # type: ignore[assignment]
        self.app_state = AppState()
        self.controller = AppController(self, self.app_state)
        self.help_window = None

        self.build_ui()

        # Set initial state of controls now that they all exist.
        self.toggle_log_path(self.log_switch)
        self._update_start_button_state()

        self.main_window.content = self.main_box  # type: ignore[attr-defined]
        self.main_window.on_close = (  # type: ignore[attr-defined]
            self.on_close
        )  # ensure graceful shutdown on window close
        self.main_window.show()  # type: ignore[attr-defined]

    def build_ui(self) -> None:
        # load logo
        photorec_cleaner_logo = toga.Image(
            "resources/WarpedWingLabsLogo_Horizontal_Compressed_W500_blur.png"
        )

        header_box = toga.Box(style=Pack(direction="row", margin=5, flex=1))
        header_box.add(
            toga.ImageView(photorec_cleaner_logo, height=75, margin_bottom=10)
        )

        # Replace instructional scroll container with a right-aligned Help button
        # spacer to push Help right
        header_box.add(toga.Box(style=Pack(flex=1)))
        help_button = toga.Button(
            "Help", on_press=self.show_help, style=Pack(height=24)
        )
        header_box.add(help_button)

        main_box = toga.Box(
            style=Pack(
                direction="column",
                margin_bottom=15,
                margin_left=10,
                margin_right=10,
                flex=1,
            )
        )
        main_box.add(header_box)
        main_box.add(toga.Divider(margin_bottom=10))

        # Directory selection
        dir_box = toga.Box(style=Pack(margin_bottom=10))
        dir_label = toga.Label(
            "PhotoRec Output Directory:", style=Pack(margin_right=10)
        )
        self.dir_path_input = toga.TextInput(readonly=True, style=Pack(flex=1))
        dir_select_button = toga.Button(
            "Select...", on_press=self.select_directory, style=Pack(margin_left=10)
        )
        dir_box.add(dir_label)
        dir_box.add(self.dir_path_input)
        dir_box.add(dir_select_button)
        main_box.add(dir_box)

        # Extension inputs
        ext_box = toga.Box(style=Pack(margin_bottom=10))
        self.cleaning_switch = toga.Switch(
            "Enable File Deletion",
            on_change=self.toggle_cleaning_controls,
            style=Pack(margin_right=10),
        )
        keep_label = toga.Label("Keep (csv):", style=Pack(margin_right=10))
        self.keep_ext_input = toga.TextInput(value="gz,sqlite", style=Pack(flex=1))
        exclude_label = toga.Label(
            "Exclude (csv):", style=Pack(margin_left=10, margin_right=10)
        )
        self.exclude_ext_input = toga.TextInput(
            value="html.gz,xml.gz", style=Pack(flex=1)
        )
        ext_box.add(self.cleaning_switch)
        ext_box.add(keep_label)
        ext_box.add(self.keep_ext_input)
        ext_box.add(exclude_label)
        ext_box.add(self.exclude_ext_input)

        self._set_initial_cleaning_controls_state()

        main_box.add(ext_box)

        # Logging controls
        log_box = toga.Box(style=Pack(margin_bottom=10))
        self.log_switch = toga.Switch(
            "Enable Logging",
            on_change=self.toggle_log_path,
            style=Pack(margin_right=10),
        )
        self.log_path_input = toga.TextInput(readonly=True, style=Pack(flex=1))
        self.log_path_button = toga.Button(
            "Select Log Folder...",
            on_press=self.select_log_folder,
            style=Pack(margin_left=10),
        )
        log_box.add(self.log_switch)
        log_box.add(self.log_path_input)
        log_box.add(self.log_path_button)
        main_box.add(log_box)

        # Reorganization controls
        reorg_box = toga.Box(style=Pack(margin_bottom=10))
        self.reorg_switch = toga.Switch(
            "Reorganize Files",
            on_change=self._update_start_button_state,
            style=Pack(margin_right=10),
        )
        batch_label = toga.Label(
            "Batch Size:", style=Pack(margin_left=10, margin_right=10)
        )
        self.batch_size_input = toga.NumberInput(value=500, min=1, style=Pack(width=80))
        reorg_box.add(self.reorg_switch)
        reorg_box.add(batch_label)
        reorg_box.add(self.batch_size_input)
        main_box.add(reorg_box)

        main_box.add(toga.Divider(margin_top=10, margin_bottom=10))

        # Running Tally
        tally_box = toga.Box(style=Pack(margin_top=10))
        self.folders_processed_label = toga.Label(
            "Folders Processed: 0", font_weight="bold", font_size=10, flex=1
        )
        self.files_kept_label = toga.Label(
            "Files Kept: 0",
            style=Pack(margin_left=20),
            font_weight="bold",
            font_size=10,
            flex=1,
        )
        self.files_deleted_label = toga.Label(
            "Files Deleted: 0",
            style=Pack(margin_left=20, font_weight="bold", font_size=10, flex=1),
        )
        self.space_saved_label = toga.Label(
            "Space Saved: 0 B",
            style=Pack(
                margin_left=20,
                font_weight="bold",
                font_size=10,
                flex=1,
                margin_right=20,
            ),
        )
        tally_box.add(self.folders_processed_label)
        tally_box.add(self.files_kept_label)
        tally_box.add(self.files_deleted_label)
        tally_box.add(self.space_saved_label)

        main_box.add(tally_box)

        # Progress bar
        self.progress_bar = toga.ProgressBar(max=100, value=0)
        self.progress_bar.style.visibility = "hidden"
        main_box.add(self.progress_bar)

        self.activity_indicator = toga.ActivityIndicator()
        self.activity_indicator.style.visibility = "hidden"
        main_box.add(self.activity_indicator)

        main_box.add(toga.Divider(margin_top=20, margin_bottom=10))

        # Status area (one label)
        status_box = toga.Box(
            style=Pack(direction="column", margin_left=7, margin_right=7), flex=2
        )
        self.guidance_label = toga.Label(
            "", style=Pack(text_align="center", font_style="italic", margin_bottom=5)
        )
        status_box.add(self.guidance_label)

        self.status_label = toga.Label(
            "Ready",
            font_family="monospace",
            font_size=10,
            color=GREEN,
            font_weight="bold",
        )

        status_box.add(self.status_label)

        scroll_container = toga.ScrollContainer(
            content=status_box, horizontal=False, vertical=True
        )

        main_box.add(scroll_container)
        main_box.add(toga.Divider(margin_top=10, margin_bottom=10))

        # Action buttons
        action_box = toga.Box(
            style=Pack(margin_top=10, flex=1, align_items="end", margin_bottom=10)
        )
        self.clean_now_button = toga.Button(
            "Process Now",
            on_press=self.clean_now_handler,
            enabled=False,
            flex=1,
            margin=5,
            font_weight="bold",
            font_size=10,
            height=30,
        )
        self.start_button = toga.Button(
            "Start Live Monitoring",
            on_press=self.start_monitoring_handler,
            enabled=False,
            flex=1,
            margin=5,
            font_weight="bold",
            font_size=10,
            height=30,
        )
        self.finish_button = toga.Button(
            "Finalize",
            on_press=self.finish_handler,
            enabled=False,
            flex=1,
            margin=5,
            font_weight="bold",
            font_size=10,
            height=30,
        )
        action_box.add(self.clean_now_button)
        action_box.add(self.start_button)
        action_box.add(self.finish_button)
        main_box.add(action_box)

        self.main_box = main_box

    async def show_help(self, widget: toga.Button) -> None:
        """Show a larger dedicated Help window with room for longer text."""
        if self.help_window is not None:
            # If already open, bring it to front
            self.help_window.show()
            return

        message = (
            "How to Use PhotoRec Refinery\n\n"
            "1) Select the PhotoRec output directory. This is the folder that contains the generated recup_dir.* subfolders.\n\n"  # noqa: E501
            "2) Configure options as needed:\n"
            "   - Enable File Deletion: Permanently delete files not worth keeping.\n"
            "   - Keep (csv): File extensions to always keep (e.g., gz, sqlite).\n"
            "   - Exclude (csv): Extensions to never keep even if they match keep (e.g., html.gz, xml.gz).\n"
            "   - Enable Logging: Write an audit log of actions.\n"
            "   - Reorganize Files: Optionally regroup files into batches for ease of review.\n\n"
            "3) Live Monitoring: Click 'Start Live Monitoring' to clean as PhotoRec recovers files. When PhotoRec is done, click 'Finalize' to stop monitoring and see a summary.\n\n"  # noqa: E501
            "4) One‑Shot: If you already have a completed PhotoRec output, click 'Process Now' to clean it immediately.\n\n"  # noqa: E501
            "Notes:\n"
            "- Deletions are permanent. Review your 'Keep' and 'Exclude' lists carefully.\n"
            "- Status shows the last action; the running tally tracks overall progress.\n"
            "- You can cancel at any time; partial results remain.\n"
        )

        # Build a simple scrollable view to handle long content gracefully
        text_label = toga.Label(message, style=Pack(padding=10))
        content_box = toga.Box(style=Pack(direction="column", flex=1))
        content_box.add(text_label)

        scroll = toga.ScrollContainer(
            content=content_box, horizontal=False, vertical=True, style=Pack(flex=1)
        )

        close_button = toga.Button(
            "Close",
            on_press=lambda w: self.help_window.close() if self.help_window else None,
            style=Pack(margin=10, width=100),
        )

        wrapper = toga.Box(style=Pack(direction="column", flex=1))
        wrapper.add(scroll)
        wrapper.add(close_button)

        self.help_window = toga.Window(
            title="PhotoRec Refinery — Help", size=(700, 500)
        )
        self.help_window.content = wrapper

        def _on_close(win: toga.Window, **kwargs: object) -> bool:
            self.help_window = None
            return True

        self.help_window.on_close = _on_close
        self.help_window.show()

    def _set_initial_cleaning_controls_state(self) -> None:
        """Sets the initial enabled state of the cleaning controls."""
        self.keep_ext_input.enabled = self.cleaning_switch.value
        self.exclude_ext_input.enabled = self.cleaning_switch.value

    def _update_start_button_state(self, widget: object = None) -> None:
        is_directory_selected = bool(self.dir_path_input.value)
        is_any_option_selected = (
            self.cleaning_switch.value
            or self.log_switch.value
            or self.reorg_switch.value
        )
        self.start_button.enabled = is_directory_selected and is_any_option_selected

    async def toggle_cleaning_controls(self, widget: toga.Switch) -> None:
        if widget.value:
            confirmed = await self.main_window.dialog(  # type: ignore[attr-defined]
                toga.ConfirmDialog(
                    "Confirm Permanent Deletion",
                    "Are you sure you want to enable file deletion? This action is permanent and cannot be undone.",
                )
            )
            if not confirmed:
                widget.value = False

        self.keep_ext_input.enabled = widget.value
        self.exclude_ext_input.enabled = widget.value
        self._update_start_button_state()

    def toggle_log_path(self, widget: toga.Switch) -> None:
        self.log_path_input.enabled = widget.value
        self.log_path_button.enabled = widget.value
        self._update_start_button_state()

    async def select_log_folder(self, widget: toga.Button) -> None:
        try:
            path = await self.main_window.dialog(  # type: ignore[attr-defined]
                toga.SelectFolderDialog(
                    title="Select Log Folder", initial_directory=None
                )
            )
            if path:
                self.log_path_input.value = str(path)
        except ValueError:
            await self.main_window.dialog(  # type: ignore[attr-defined]
                toga.InfoDialog("Cancelled", "Log folder selection was cancelled.")
            )

    async def select_directory(self, widget: toga.Button) -> None:
        try:
            path = await self.main_window.dialog(  # type: ignore[attr-defined]
                toga.SelectFolderDialog(
                    title="Select PhotoRec Output Directory", initial_directory=None
                )
            )
            if path:
                self.dir_path_input.value = str(path)
                self.log_path_input.value = str(path)
                self.controller.set_cleaner(str(path))
                self.controller.start_folder_polling()
                self._update_start_button_state()

        except ValueError:
            await self.main_window.dialog(  # type: ignore[attr-defined]
                toga.InfoDialog("Cancelled", "Directory selection was cancelled.")
            )
        self.app_state.reset()
        self.update_tally()

    def start_monitoring_handler(self, widget: toga.Button) -> None:
        self.clean_now_button.enabled = False
        self.finish_button.enabled = True
        self.guidance_label.text = (
            "Live monitoring started. Click 'Finalize' when PhotoRec is finished."
        )
        self.status_label.text = "Monitoring..."  # Set initial status immediately
        self.controller.start_monitoring()

        # Change button to Cancel
        self.start_button.text = "Cancel"
        self.start_button.on_press = self.cancel_handler

    def cancel_handler(self, widget: toga.Button) -> None:
        """Immediately cancels all processing."""
        self.controller.cancel()

        self.activity_indicator.stop()
        self.activity_indicator.style.visibility = "hidden"
        self.progress_bar.style.visibility = "hidden"

        # Reset UI elements to their pre-monitoring state
        self.status_label.text = "Cancelled."
        self.guidance_label.text = ""
        self.finish_button.enabled = False

        # Reset start button
        self.start_button.text = "Start Live Monitoring"
        self.start_button.on_press = self.start_monitoring_handler
        self._update_start_button_state()

        # Restart polling to check for existing folders to enable the "Process Now" button
        self.controller.start_folder_polling()

    def _set_status_text_threadsafe(self, message: str) -> None:
        # Keep status concise to avoid layout thrashing
        self.status_label.text = shorten_path(message, maxlen=120)

    def update_tally(self) -> None:
        self.folders_processed_label.text = (
            f"Folders Processed: {len(self.app_state.cleaned_folders)}"
        )
        self.files_kept_label.text = f"Files Kept: {self.app_state.total_kept_count}"
        self.files_deleted_label.text = (
            f"Files Deleted: {self.app_state.total_deleted_count}"
        )
        self.space_saved_label.text = (
            f"Space Saved: {self._format_size(self.app_state.total_deleted_size)}"
        )

    def _format_size(self, size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        if size_bytes < 1024**2:
            return f"{size_bytes / 1024:.1f} KB"
        if size_bytes < 1024**3:
            return f"{size_bytes / 1024**2:.1f} MB"
        return f"{size_bytes / 1024**3:.1f} GB"

    async def finish_handler(self, widget: toga.Button) -> None:
        self.finish_button.enabled = False
        self.clean_now_button.enabled = False

        self.progress_bar.value = 0
        self.progress_bar.style.visibility = "visible"
        self.activity_indicator.style.visibility = "visible"
        self.activity_indicator.start()

        await self.controller.finish_processing()

        # --- Exit processing state ---
        self.activity_indicator.stop()
        self.activity_indicator.style.visibility = "hidden"
        self.progress_bar.style.visibility = "hidden"

        # Show final report (only if not cancelled)
        if not self.app_state.cancelled:
            self._show_final_report()

        # get_recup_dirs can be slow, run it in a thread
        base_dir = self.dir_path_input.value
        recup_dirs = await asyncio.to_thread(get_recup_dirs, base_dir)
        self.clean_now_button.enabled = bool(recup_dirs)

        # Reset start button
        self.start_button.text = "Start Live Monitoring"
        self.start_button.on_press = self.start_monitoring_handler
        self._update_start_button_state()  # This will set the enabled state correctly

        self.finish_button.enabled = False
        self.app_state.reset()
        self.guidance_label.text = ""
        self.update_tally()

    async def clean_now_handler(self, widget: toga.Button) -> None:
        """Handler for the 'Clean Now' button to process existing folders."""
        # --- Enter processing state ---
        self.clean_now_button.enabled = False
        self.finish_button.enabled = False
        self.start_button.text = "Cancel"
        self.start_button.on_press = self.cancel_handler
        self.start_button.enabled = True

        self.progress_bar.value = 0
        self.progress_bar.style.visibility = "visible"
        self.activity_indicator.style.visibility = "visible"
        self.activity_indicator.start()

        await self.controller.perform_one_shot_clean()

        # --- Exit processing state (unconditionally) ---
        self.activity_indicator.stop()
        self.activity_indicator.style.visibility = "hidden"
        self.progress_bar.style.visibility = "hidden"

        # Reset start button
        self.start_button.text = "Start Live Monitoring"
        self.start_button.on_press = self.start_monitoring_handler
        self._update_start_button_state()

        # clean_now is disabled because folders are gone
        self.clean_now_button.enabled = False

        self.app_state.reset()
        self.guidance_label.text = ""
        self.update_tally()

    def _show_final_report(self) -> None:
        report_title = "Processing Complete"
        report_body = (
            f"Photorec Cleaning Complete\n\n"
            f"Folders Processed: {len(self.app_state.cleaned_folders)}\n"
            f"Files Kept: {self.app_state.total_kept_count}\n"
            f"Files Deleted: {self.app_state.total_deleted_count}\n"
            f"Total Space Saved: {self._format_size(self.app_state.total_deleted_size)}"
        )
        asyncio.run_coroutine_threadsafe(
            self._show_dialog_async(report_title, report_body),
            asyncio.get_running_loop(),
        )

    def update_progress(self, value: int, max_value: int) -> None:
        self.progress_bar.max = max_value
        self.progress_bar.value = value

    async def _update_progress_async(self, value: int, max_value: int) -> None:
        self.update_progress(value, max_value)

    def update_status(self, message: str) -> None:
        # called from file_utils cleaners which might run in the main thread
        self.status_label.text = shorten_path(message, maxlen=120)

    async def _update_tally_async(self) -> None:
        """Async version of update_tally to be called from other threads."""
        self.update_tally()

    async def _set_status_text_async(self, message: str) -> None:
        """Async version of setting status text to be called from other threads."""
        self.status_label.text = shorten_path(message, maxlen=120)

    async def _show_dialog_async(self, title: str, message: str) -> None:
        """Creates and shows a dialog from a coroutine, ensuring it's on the main thread."""
        dialog = toga.InfoDialog(title, message)
        await self.main_window.dialog(dialog)  # type: ignore[attr-defined]

    def on_close(self, window: toga.Window, **kwargs: object) -> bool:
        self.controller.on_close()
        return True


def main() -> None:
    print("--- Entering main function ---")
    # app icon path must be absolute to be found reliably
    # Explicitly add the .icns extension for macOS
    icon_path = Path(__file__).parent / "resources"

    # --- DEBUGGING: Check if the path is correct and the file exists ---
    print(f"Attempting to load icon from absolute path: {icon_path}")
    print(f"Does icon file exist? {Path.exists(icon_path)}")
    # --- END DEBUGGING ---
    app = PhotoRecCleanerApp(
        formal_name="PhotoRec Refinery",
        app_id="org.beeware.photorec_refinery",
        app_name="photorec_refinery",
        icon=str(icon_path),
    )
    app.main_loop()


if __name__ == "__main__":
    main()
