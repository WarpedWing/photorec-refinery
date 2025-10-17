"""
Toga GUI for PhotoRec Refinery.

"""

from __future__ import annotations

import asyncio
import contextlib
import webbrowser
from pathlib import Path

import toga
from toga.constants import GREEN
from toga.style import Pack

from photorec_refinery.app_state import AppState
from photorec_refinery.controller import AppController
from photorec_refinery.file_utils import get_recup_dirs
from photorec_refinery.gui_utils import tail_truncate


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
    folders_processed_value: toga.Label
    files_kept_value: toga.Label
    files_deleted_value: toga.Label
    space_saved_value: toga.Label
    progress_bar: toga.ProgressBar
    activity_indicator: toga.ActivityIndicator
    guidance_label: toga.Label
    status_label: toga.Label
    cancel_button: toga.Button
    live_monitor_button: toga.Button
    process_button: toga.Button
    help_window: toga.Window | None
    active_task: asyncio.Task | None
    drop_updates: bool
    _dir_path_full: str
    _log_path_full: str
    report_window: toga.Window | None
    _suppress_delete_warning: bool

    def startup(self) -> None:
        self.main_window = toga.MainWindow(
            title=self.formal_name
        )  # type: ignore[assignment]
        self.app_state = AppState()
        self.controller = AppController(self, self.app_state)
        self.help_window = None
        self.report_window = None
        self.active_task = None
        self.drop_updates = False
        self._dir_path_full = ""
        self._log_path_full = ""
        self._suppress_delete_warning = False

        self.build_ui()

        # Set initial state of controls now that they all exist.
        self.toggle_log_path(self.log_switch)
        self._update_start_button_state()

        # Apply platform-specific styling
        self._apply_platform_theme()

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

        # Help button
        # spacer to push Help right
        header_box.add(toga.Box(style=Pack(flex=1)))
        help_button = toga.Button(
            "Help", on_press=self.show_help, style=Pack(height=24)
        )
        header_box.add(help_button)

        # Outer box
        main_box = toga.Box(style=Pack(direction="column", flex=1))
        # Inner content wrapper
        content_box = toga.Box(style=Pack(direction="column", flex=1, margin=12))
        content_box.add(header_box)
        content_box.add(toga.Divider(margin_bottom=10))

        # Directory selection
        dir_box = toga.Box(style=Pack(margin_bottom=10))
        dir_label = toga.Label(
            "PhotoRec Output Directory:", style=Pack(margin_right=10)
        )
        # Show truncated path; store full separately
        self._updating_dir_field = False
        self.dir_path_input = toga.TextInput(
            readonly=False, on_change=self.on_dir_path_changed, style=Pack(flex=1)
        )
        dir_select_button = toga.Button(
            "Select...", on_press=self.select_directory, style=Pack(margin_left=10)
        )
        dir_box.add(dir_label)
        dir_box.add(self.dir_path_input)
        dir_box.add(dir_select_button)
        content_box.add(dir_box)

        # Extension inputs
        ext_box = toga.Box(style=Pack(margin_bottom=10))
        self.cleaning_switch = toga.Switch(
            "Enable File Deletion",
            on_change=self.toggle_cleaning_controls,
            style=Pack(margin_right=10),
        )
        keep_label = toga.Label("Keep (csv or lines):", style=Pack(margin_right=10))
        self.keep_ext_input = toga.MultilineTextInput(
            value="", placeholder="gz\nsqlite", style=Pack(flex=1, height=60)
        )
        self.keep_ext_input.enabled = self.cleaning_switch.value
        exclude_label = toga.Label(
            "Exclude (csv or lines):", style=Pack(margin_left=10, margin_right=10)
        )
        self.exclude_ext_input = toga.MultilineTextInput(
            value="", placeholder="html.gz\nxml.gz", style=Pack(flex=1, height=60)
        )
        self.exclude_ext_input.enabled = self.cleaning_switch.value
        ext_box.add(self.cleaning_switch)
        ext_box.add(keep_label)
        ext_box.add(self.keep_ext_input)
        ext_box.add(exclude_label)
        ext_box.add(self.exclude_ext_input)

        self._set_initial_cleaning_controls_state()

        content_box.add(ext_box)

        # Logging controls
        log_box = toga.Box(style=Pack(margin_bottom=10))
        self.log_switch = toga.Switch(
            "Enable Logging",
            on_change=self.toggle_log_path,
            style=Pack(margin_right=10),
        )
        # Show truncated path; store full separately
        self._updating_log_field = False
        self.log_path_input = toga.TextInput(
            readonly=False, on_change=self.on_log_path_changed, style=Pack(flex=1)
        )
        self.log_path_button = toga.Button(
            "Select Log Folder...",
            on_press=self.select_log_folder,
            style=Pack(margin_left=10),
        )
        log_box.add(self.log_switch)
        log_box.add(self.log_path_input)
        log_box.add(self.log_path_button)
        content_box.add(log_box)

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
        # Batch size for reorganization. Using integer semantics.
        self.batch_size_input = toga.NumberInput(value=500, min=1, style=Pack(width=80))
        reorg_box.add(self.reorg_switch)
        reorg_box.add(batch_label)
        reorg_box.add(self.batch_size_input)
        content_box.add(reorg_box)

        content_box.add(toga.Divider(margin_top=10, margin_bottom=10))

        # Running Tally
        tally_row = toga.Box(style=Pack(direction="row", margin_top=8))

        def stat(title: str) -> tuple[toga.Box, toga.Label]:
            title_lbl = toga.Label(title, style=Pack(font_size=9, color="#9aa0a6"))
            value_lbl = toga.Label(
                "0", style=Pack(font_weight="bold", font_family="monospace")
            )
            col = toga.Box(style=Pack(direction="column", flex=1, margin_right=10))
            col.add(title_lbl)
            col.add(value_lbl)
            return col, value_lbl

        col1, self.folders_processed_value = stat("Folders Processed")
        col2, self.files_kept_value = stat("Files Kept")
        col3, self.files_deleted_value = stat("Files Deleted")
        col4, self.space_saved_value = stat("Space Saved")
        tally_row.add(col1)
        tally_row.add(col2)
        tally_row.add(col3)
        tally_row.add(col4)

        content_box.add(tally_row)

        # Progress bar
        self.progress_bar = toga.ProgressBar(max=100, value=0)
        self.progress_bar.style.visibility = "hidden"
        content_box.add(self.progress_bar)

        content_box.add(toga.Divider(margin_top=20, margin_bottom=10))

        # Status area (one label)
        status_box = toga.Box(
            style=Pack(
                direction="column",
                margin_left=7,
                margin_right=7,
                flex=1,
            )
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

        # activity spinner
        self.activity_indicator = toga.ActivityIndicator()
        self.activity_indicator.style.visibility = "hidden"
        spinner_box = toga.Box(
            style=Pack(
                flex=1,
                direction="column",
                justify_content="center",
                align_items="center",
                margin=5,
            )
        )
        spinner_box.add(self.activity_indicator)
        status_box.add(spinner_box)

        scroll_container = toga.ScrollContainer(
            content=status_box, horizontal=False, vertical=True
        )

        content_box.add(scroll_container)
        content_box.add(toga.Divider(margin_top=10, margin_bottom=10))

        # Action buttons
        action_box = toga.Box(
            style=Pack(margin_top=10, flex=1, align_items="end", margin_bottom=10)
        )
        self.cancel_button = toga.Button(
            "Cancel",
            on_press=self.cancel_handler,
            enabled=False,
            flex=1,
            margin=5,
            font_weight="bold",
            font_size=10,
            height=30,
        )
        self.live_monitor_button = toga.Button(
            "Live Monitor",
            on_press=self.start_monitoring_handler,
            enabled=False,
            flex=1,
            margin=5,
            font_weight="bold",
            font_size=10,
            height=30,
        )
        self.process_button = toga.Button(
            "Process",
            on_press=self._process_or_finalize_handler,
            enabled=False,
            flex=1,
            margin=5,
            font_weight="bold",
            font_size=10,
            height=30,
        )
        action_box.add(self.cancel_button)
        action_box.add(self.live_monitor_button)
        action_box.add(self.process_button)
        content_box.add(action_box)

        # Add padded content to the outer main box
        main_box.add(content_box)

        self.main_box = main_box

    async def show_help(self, widget: toga.Button) -> None:
        """Show a larger dedicated Help window with room for longer text."""
        if self.help_window is not None:
            # If already open, bring it to front
            self.help_window.show()
            return

        heading = "How to Use PhotoRec Refinery"
        message = (
            "1) Select the PhotoRec output directory. This is the folder that contains the generated recup_dir.* subfolders.\n\n"  # noqa: E501
            "2) Configure options as needed:\n"
            "   - Enable File Deletion: Permanently delete unwanted files.\n"
            "   - Keep (csv): File extensions to keep. Delete all others.\n"
            "   - Exclude (csv): Keep all files except these. Can be used with keep to refine the query.\n"
            "   - Enable Logging: Write an audit log of file actions.\n"
            "   - Reorganize Files: Reorganize files into folders named by filetype.\n"
            "   - Batch Size: The number of files you want in each subfolder.\n\n"
            "3) Live Monitoring: Click 'Live Monitor' to clean as PhotoRec recovers files.\n"
            "   - When PhotoRec is done, click 'Finalize'.\n\n"
            "4) Process: If you already have a completed PhotoRec output, click 'Process'.\n\n"
            "Need More Help?\n"
            "- Click the buttons below to email me or visit my GitHub.\n"
            "- noel@warpedwinglabs.com\n"
            "- https://github.com/WarpedWing\n\n"
        )

        # Help text box
        heading_label = toga.Label(
            heading, style=Pack(margin=(10, 10), font_weight="bold", font_size=16)
        )
        text_label = toga.Label(message, style=Pack(margin=(0, 10)))
        content_box = toga.Box(style=Pack(direction="column", flex=1))
        content_box.add(heading_label)
        content_box.add(text_label)

        scroll = toga.ScrollContainer(
            content=content_box, horizontal=False, vertical=True, style=Pack(flex=1)
        )

        # Clickable links
        def _open(url: str) -> None:
            with contextlib.suppress(Exception):
                webbrowser.open(url)

        links_box = toga.Box(style=Pack(direction="row", margin=10))
        email_btn = toga.Button(
            "Email",
            on_press=lambda w: _open(
                "mailto:noel@warpedwinglabs.com?subject=PhotoRec%20Refinery%20Help"
            ),
            style=Pack(margin_right=10, height=28),
        )
        github_btn = toga.Button(
            "GitHub",
            on_press=lambda w: _open("https://github.com/WarpedWing/photorec-refinery"),
            style=Pack(height=28),
        )
        links_box.add(email_btn)
        links_box.add(github_btn)

        close_button = toga.Button(
            "Close",
            on_press=lambda w: self.help_window.close() if self.help_window else None,
            style=Pack(margin=10, width=100),
        )

        wrapper = toga.Box(style=Pack(direction="column", flex=1))
        wrapper.add(scroll)
        wrapper.add(links_box)
        wrapper.add(close_button)

        self.help_window = toga.Window(
            title="PhotoRec Refinery — Help", size=(700, 500)
        )
        self.help_window.content = wrapper

        def _on_close(win: toga.Window, **kwargs: object) -> bool:
            self.help_window = None
            return True

        self.help_window.on_close = _on_close  # type: ignore[attr-defined]
        self.help_window.show()

    def _set_initial_cleaning_controls_state(self) -> None:
        """Sets the initial enabled state of the cleaning controls."""
        self.keep_ext_input.enabled = self.cleaning_switch.value
        self.exclude_ext_input.enabled = self.cleaning_switch.value

    # Removed ghost-based styling; rely on placeholders while disabled

    # --- Paths: getters that return full paths regardless of display truncation ---
    def get_base_dir(self) -> str:
        return self._dir_path_full or self.dir_path_input.value or ""

    def get_log_dir(self) -> str:
        return self._log_path_full or self.log_path_input.value or ""

    # --- Path inputs: change handlers and display helpers ---
    def _set_dir_display_from_full(self) -> None:
        if not self._dir_path_full:
            self.dir_path_input.value = ""
            return
        self._updating_dir_field = True
        try:
            self.dir_path_input.value = tail_truncate(self._dir_path_full, maxlen=80)
        finally:
            self._updating_dir_field = False

    def _set_log_display_from_full(self) -> None:
        if not self._log_path_full:
            self.log_path_input.value = ""
            return
        self._updating_log_field = True
        try:
            self.log_path_input.value = tail_truncate(self._log_path_full, maxlen=80)
        finally:
            self._updating_log_field = False

    def on_dir_path_changed(self, widget: toga.TextInput) -> None:
        if self._updating_dir_field:
            return
        full = (widget.value or "").strip()
        self._dir_path_full = full
        # If it's a valid directory, wire up the cleaner and polling
        if full and Path(full).is_dir():
            self.controller.set_cleaner(full)
            self.controller.start_folder_polling()
            self._update_start_button_state()

    def on_log_path_changed(self, widget: toga.TextInput) -> None:
        if self._updating_log_field:
            return
        full = (widget.value or "").strip()
        self._log_path_full = full

    # --- ProgressBar appearance ---
    def set_progress_color(self, color_name: str | None) -> None:
        """Optionally tint the progress bar (best-effort; platform-dependent)."""
        try:
            if color_name == "green":
                # Prefer tinting the bar, not the background, if supported
                with contextlib.suppress(Exception):
                    self.progress_bar.style.color = (
                        "#2e7d32"  # bar color (backend-dependent)
                    )
                # Reset background to default to emphasize bar
                self.progress_bar.style.background_color = None  # type: ignore[assignment]
            else:
                # Reset to default style
                self.progress_bar.style.background_color = None  # type: ignore[assignment]
                with contextlib.suppress(Exception):
                    self.progress_bar.style.color = None  # type: ignore[assignment]
        except Exception:
            # Some backends may not support setting colors on native widgets
            pass

    # --- Platform styling ---
    def _apply_platform_theme(self) -> None:
        """Apply a dark theme on all platforms."""
        try:
            dark_bg = "#1e1e1e"
            light_fg = "#e0e0e0"
            # Backgrounds
            self.main_box.style.background_color = dark_bg
            # Key labels
            self.folders_processed_value.color = light_fg
            self.files_kept_value.color = light_fg
            self.files_deleted_value.color = light_fg
            self.space_saved_value.color = light_fg
            self.guidance_label.color = light_fg
            # Inputs (best-effort)
            self.dir_path_input.style.background_color = "#2b2b2b"
            self.dir_path_input.style.color = light_fg
            self.log_path_input.style.background_color = "#2b2b2b"
            self.log_path_input.style.color = light_fg
        except Exception:
            # If any of these style tweaks aren't supported on the backend, ignore silently.
            pass

    def _update_start_button_state(self, widget: object = None) -> None:
        is_directory_selected = bool(self.dir_path_input.value)
        is_any_option_selected = (
            self.cleaning_switch.value
            or self.log_switch.value
            or self.reorg_switch.value
        )
        self.live_monitor_button.enabled = (
            is_directory_selected and is_any_option_selected
        )

    async def toggle_cleaning_controls(self, deleteSwitch: toga.Switch) -> None:
        # Confirm once per app session
        if deleteSwitch.value and not self._suppress_delete_warning:
            confirmed = await self.main_window.dialog(  # type: ignore[attr-defined]
                toga.ConfirmDialog(
                    "Confirm Permanent Deletion",
                    "Are you sure you want to enable file deletion? This action is permanent and cannot be undone.",
                )
            )
            if not confirmed:
                deleteSwitch.value = False
                return
            self._suppress_delete_warning = True

        default_keep_ph = "gz\nsqlite"
        default_excl_ph = "html.gz\nxml.gz"

        self.keep_ext_input.enabled = deleteSwitch.value
        self.exclude_ext_input.enabled = deleteSwitch.value
        # If enabling deletion, clear the placeholders
        if deleteSwitch.value:
            if self.keep_ext_input.placeholder != default_keep_ph:
                self.keep_ext_input.value = self.keep_ext_input.placeholder
            else:
                self.keep_ext_input.value = ""
            if self.exclude_ext_input.placeholder != default_excl_ph:
                self.exclude_ext_input.value = self.exclude_ext_input.placeholder
            else:
                self.exclude_ext_input.value = ""
            self.keep_ext_input.placeholder = ""
            self.exclude_ext_input.placeholder = ""
        else:
            # If disabling, restore examples if fields are empty
            if not self.keep_ext_input.value.strip():
                self.keep_ext_input.placeholder = default_keep_ph
            if not self.exclude_ext_input.value.strip():
                self.exclude_ext_input.placeholder = default_excl_ph
            if self.keep_ext_input.value.strip():
                self.keep_ext_input.placeholder = self.keep_ext_input.value.strip()
            if self.exclude_ext_input.value.strip():
                self.exclude_ext_input.placeholder = (
                    self.exclude_ext_input.value.strip()
                )
            self.keep_ext_input.value = ""
            self.exclude_ext_input.value = ""

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
                self._log_path_full = str(path)
                self._set_log_display_from_full()
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
                # Store full paths, but display short versions
                self._dir_path_full = str(path)
                self._log_path_full = str(path)
                self._set_dir_display_from_full()
                self._set_log_display_from_full()
                self.controller.set_cleaner(self._dir_path_full)
                self.controller.start_folder_polling()
                self._update_start_button_state()

        except ValueError:
            await self.main_window.dialog(  # type: ignore[attr-defined]
                toga.InfoDialog("Cancelled", "Directory selection was cancelled.")
            )
        self.app_state.reset()
        self.update_tally()

    def start_monitoring_handler(self, widget: toga.Button) -> None:
        self.drop_updates = False
        self.process_button.text = "Finalize"
        self.process_button.enabled = True
        self.cancel_button.enabled = True
        self.live_monitor_button.enabled = False
        self.guidance_label.text = (
            "Live monitoring started. Click 'Finalize' when PhotoRec is finished."
        )
        self.status_label.text = "Monitoring..."  # Set initial status immediately
        self.controller.start_monitoring()

    def cancel_handler(self, widget: toga.Button) -> None:
        """Cancel immediately; show 'Cancelling…' right away; then return."""
        # Gate all further status/progress updates first, so nothing overwrites our message
        self.drop_updates = True
        self.status_label.text = "Cancelling..."
        self.guidance_label.text = "Cancellation in progress — this may take a moment."
        self.cancel_button.enabled = False
        self.process_button.enabled = False
        self.live_monitor_button.enabled = False
        # UI will update immediately; cleanup runs in background

        # Signal controller + workers to stop and close logs, then finalize asynchronously
        self.controller.cancel()
        asyncio.create_task(self._post_cancel_cleanup())

    async def _post_cancel_cleanup(self) -> None:
        """Wait for active work to stop, then reset UI and resume polling."""
        if self.active_task and not self.active_task.done():
            with contextlib.suppress(asyncio.CancelledError):
                await self.active_task
        self.active_task = None

        # Stop indicators now that work has ceased
        self.activity_indicator.stop()
        self.activity_indicator.style.visibility = "hidden"
        self.progress_bar.style.visibility = "hidden"

        # Reset UI elements to their pre-monitoring state
        self.status_label.text = "Cancelled."
        self.guidance_label.text = ""
        self.process_button.text = "Process"
        self.process_button.enabled = False
        self._update_start_button_state()  # updates live_monitor_button

        # Restart polling to check for existing folders to enable the Process button
        self.controller.start_folder_polling()

    def _set_status_text_threadsafe(self, message: str) -> None:
        # Keep status concise to avoid layout thrashing
        if self.drop_updates or self.app_state.cancelled:
            return
        self.status_label.text = tail_truncate(message, maxlen=120)

    def update_tally(self) -> None:
        self.folders_processed_value.text = f"{len(self.app_state.cleaned_folders)}"
        self.files_kept_value.text = f"{self.app_state.total_kept_count}"
        self.files_deleted_value.text = f"{self.app_state.total_deleted_count}"
        self.space_saved_value.text = (
            f"{self._format_size(self.app_state.total_deleted_size)}"
        )

    def _format_size(self, size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        if size_bytes < 1024**2:
            return f"{size_bytes / 1024:.1f} KB"
        if size_bytes < 1024**3:
            return f"{size_bytes / 1024**2:.1f} MB"
        return f"{size_bytes / 1024**3:.1f} GB"

    async def finish_handler(self, widget: toga.Button | None = None) -> None:
        self.process_button.enabled = False
        self.live_monitor_button.enabled = False

        self.progress_bar.value = 0
        self.progress_bar.style.visibility = "visible"
        self.activity_indicator.style.visibility = "visible"
        self.activity_indicator.start()
        try:
            await self.controller.finish_processing()
        except asyncio.CancelledError:
            # Swallow cancellation; cancel handler handles UI teardown
            return

        # --- Exit processing state ---
        self.activity_indicator.stop()
        self.activity_indicator.style.visibility = "hidden"
        self.progress_bar.style.visibility = "hidden"

        # Show final report (only if not cancelled)
        if not self.app_state.cancelled:
            self._show_final_report()

        # get_recup_dirs can be slow, run it in a thread
        base_dir = self.get_base_dir()
        recup_dirs = await asyncio.to_thread(get_recup_dirs, base_dir)
        self.process_button.enabled = bool(recup_dirs)

        # Reset buttons
        self.process_button.text = "Process"
        self._update_start_button_state()  # enable Live Monitor if allowed
        self.cancel_button.enabled = False
        self.app_state.reset()
        self.guidance_label.text = ""
        self.update_tally()
        self.active_task = None

    async def clean_now_handler(self, widget: toga.Button | None = None) -> None:
        """Handler for the 'Clean Now' button to process existing folders."""
        # --- Enter processing state ---
        self.drop_updates = False
        self.process_button.enabled = False
        self.live_monitor_button.enabled = False
        self.cancel_button.enabled = True

        # Pause folder polling during one-shot processing to avoid UI races
        self.controller.stop_folder_polling()

        self.progress_bar.value = 0
        self.progress_bar.style.visibility = "visible"
        self.activity_indicator.style.visibility = "visible"
        self.activity_indicator.start()

        try:
            await self.controller.perform_one_shot_clean()
        except asyncio.CancelledError:
            # Swallow cancellation; cancel handler handles UI teardown
            return

        # --- Exit processing state (unconditionally) ---
        self.activity_indicator.stop()
        self.activity_indicator.style.visibility = "hidden"
        self.progress_bar.style.visibility = "hidden"

        # Reset buttons
        self.process_button.text = "Process"
        self._update_start_button_state()

        # processing is disabled because folders are gone
        self.process_button.enabled = False

        self.app_state.reset()
        self.guidance_label.text = ""
        self.update_tally()
        self.active_task = None

        # Resume polling to reflect current folder state
        self.controller.start_folder_polling()

    def _process_or_finalize_handler(self, widget: toga.Button) -> None:
        """Decide whether to process immediately or finalize monitoring."""
        monitoring_active = bool(
            self.controller.monitoring_task
            and not self.controller.monitoring_task.done()
        )
        if monitoring_active:
            # Run finalize path
            self.active_task = asyncio.create_task(self.finish_handler(None))
        else:
            # Run one-shot processing path
            self.active_task = asyncio.create_task(self.clean_now_handler(None))

    def _show_final_report(self) -> None:
        """Show the original compact popup report with prior logic."""
        report_title = "Processing Complete"
        report_body = (
            f"Photorec Cleaning Complete\n\n"
            f"Folders Processed: {len(self.app_state.cleaned_folders)}\n"
        )
        if self.app_state.total_deleted_count > 0:
            report_body += (
                f"Files Kept: {self.app_state.total_kept_count}\n"
                f"Files Deleted: {self.app_state.total_deleted_count}\n"
                f"Total Space Saved: {self._format_size(self.app_state.total_deleted_size)}"
            )
        else:
            report_body += f"Files Scanned: {self.app_state.total_kept_count}\n"
        asyncio.run_coroutine_threadsafe(
            self._show_dialog_async(report_title, report_body),
            asyncio.get_running_loop(),
        )

    def update_progress(self, value: int, max_value: int) -> None:
        if self.drop_updates or self.app_state.cancelled:
            return
        self.progress_bar.max = max_value
        self.progress_bar.value = value

    async def _update_progress_async(self, value: int, max_value: int) -> None:
        self.update_progress(value, max_value)

    def update_status(self, message: str) -> None:
        # called from file_utils cleaners which might run in the main thread
        if self.drop_updates or self.app_state.cancelled:
            return
        self.status_label.text = tail_truncate(message, maxlen=120)

    async def _update_tally_async(self) -> None:
        """Async version of update_tally to be called from other threads."""
        if self.drop_updates or self.app_state.cancelled:
            return
        self.update_tally()

    async def _set_status_text_async(self, message: str) -> None:
        """Async version of setting status text to be called from other threads."""
        if self.drop_updates or self.app_state.cancelled:
            return
        self.status_label.text = tail_truncate(message, maxlen=120)

    async def _show_dialog_async(self, title: str, message: str) -> None:
        """Creates and shows a dialog from a coroutine, ensuring it's on the main thread."""
        dialog = toga.InfoDialog(title, message)
        await self.main_window.dialog(dialog)  # type: ignore[attr-defined]

    def on_close(self, window: toga.Window, **kwargs: object) -> bool:
        self.controller.on_close()
        return True


def main() -> None:
    # Determine the icon path - Briefcase packages the icon in resources
    icon_path = Path(__file__).parent / "resources" / "photorec-refinery"

    app = PhotoRecCleanerApp(
        formal_name="PhotoRec Refinery",
        app_id="org.beeware.photorec_refinery",
        app_name="photorec-refinery",
        icon=str(icon_path),
    )
    app.main_loop()


if __name__ == "__main__":
    main()
