"""
Handles the console user interface for the PhotoRec Cleaner.

This module provides functions for printing a real-time status box,
formatting output with colors, and managing background threads for UI updates
and user input.
"""

import os
import re
import time
from threading import Thread

# --- ANSI color codes ---
RED = "\033[91m"
GREEN = "\033[92m"
BLUE = "\033[94m"
GRAY = "\033[90m"
BOLD = "\033[1m"
RESET = "\033[0m"

BOX_WIDTH = 70
SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


# The number of lines the status box will occupy.
# (top + title + 4 stats + separator + activity + bottom)
BOX_HEIGHT = 1 + 1 + 4 + 1 + 1 + 1


def fit_to_width(text, width):
    """Truncate a string to a given visible width, handling ANSI codes."""
    visible_text = "".join(re.split(r"\x1b\[[0-9;]*m", text))

    if len(visible_text) <= width:
        return text

    # Truncate the middle
    end_len = (width - 3) // 2  # 3 for '...'
    start_len = width - end_len - 3
    truncated_text = f"{visible_text[:start_len]}...{visible_text[-end_len:]}"

    # Re-apply start color if any
    match = re.match(r"\x1b\[[0-9;]*m", text)
    color_code = match.group(0) if match else ""

    return f"{color_code}{truncated_text}{RESET}"


def format_size(bytes_size):
    """
    Converts a size in bytes to a human-readable string (KB, MB, GB, etc.).

    Args:
        bytes_size (int): The size in bytes.

    Returns:
        str: A human-readable string representation of the size.
    """
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_size < 1024:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024
    return f"{bytes_size:.2f} PB"


def print_intro(output_dir):
    """
    Prints the initial welcome banner for the application.

    Args:
        output_dir (str): The directory being monitored.
    """
    print(f"\n{'=' * (BOX_WIDTH + 2)}")
    print(f"{f'{BOLD}PhotoRec Cleaner v0.2{RESET}':^{BOX_WIDTH + 10}}")
    print(f"{'=' * (BOX_WIDTH + 2)}")
    print(f"  Output directory: {GREEN}{os.path.abspath(output_dir)}{RESET}")
    print(
        f"  Press {BLUE}'y' + Enter{RESET} when PhotoRec is done to finish cleaning.\n"
    )


def print_status_live(state):
    """
    Draws the main status box UI in the console.

    This function uses ANSI escape codes to move the cursor, clear previous
    output, and draw a real-time status box with stats and a spinner.
    """
    spinner = SPINNER_FRAMES[state.spinner_index % len(SPINNER_FRAMES)]
    state.spinner_index += 1

    if state.app_state == "idle":
        spinner_color = GRAY
    elif state.app_state == "monitoring":
        spinner_color = BLUE
    else:  # cleaning or final pass
        spinner_color = GREEN

    # Move cursor up and clear
    print(f"\033[{BOX_HEIGHT}A", end="")
    for _ in range(BOX_HEIGHT):
        print("\033[K")
    print(f"\033[{BOX_HEIGHT}A", end="")

    # Draw box
    print("+" + "-" * BOX_WIDTH + "+")
    title = f"{BOLD}PhotoRec Cleaner Status {spinner_color}[{spinner}]{RESET}"
    # The width for centering is adjusted to account for non-printable ANSI codes
    print(f"|{title:^{BOX_WIDTH + 13}}|")
    line1 = f"Folders cleaned      : {len(state.cleaned_folders)}"
    line2 = f"Total files deleted  : {state.total_deleted_count}"
    line3 = f"Total files kept     : {state.total_kept_count}"
    line4 = f"Total space freed    : {format_size(state.total_deleted_size)}"
    for line in [line1, line2, line3, line4]:
        print(f"| {line:<{BOX_WIDTH - 2}} |")
    print("+" + "-" * BOX_WIDTH + "+")
    activity_line = f"  {state.current_activity}"
    print(f"| {fit_to_width(activity_line, BOX_WIDTH - 2):<{BOX_WIDTH - 2}} |")
    print("+" + "-" * BOX_WIDTH + "+")


def clear_status_box():
    """Move cursor up and clear the entire status box area."""
    print(f"\033[{BOX_HEIGHT}A", end="")
    for _ in range(BOX_HEIGHT):
        print("\033[K", end="")


def clear_screen():
    """Clears the entire terminal screen."""
    os.system("cls" if os.name == "nt" else "clear")


def ui_updater(state):
    """Continuously refresh UI with spinner animation."""
    while not state.final_cleanup:
        print_status_live(state)
        time.sleep(0.1)
    print_status_live(state)  # final paint


def input_watcher(state, ui_thread):
    """
    A thread target that waits for the user to input 'y' to signal completion.

    Args:
        state (AppState): The shared application state.
    """
    while not state.final_cleanup:
        try:
            line = input().strip().lower()
            if line == "y":
                # Move cursor up to overwrite the 'y' and clear the line
                print("\033[A\033[K", end="", flush=True)

                # Stop the UI thread and wait for it to finish
                state.final_cleanup = True
                ui_thread.join()

                # Now that the UI is stopped, provide immediate feedback
                print(f"{BOLD}Finalizing, please wait...{RESET}")
                state.ready_for_final_cleanup = True
        except EOFError:
            break


def start_ui_threads(state):
    """
    Initializes and starts the background threads for UI and user input.

    Args:
        state (AppState): The shared application state to pass to the threads.

    Returns:
        tuple: A tuple containing the watcher_thread and ui_thread objects.
    """
    ui_thread = Thread(target=ui_updater, args=(state,), daemon=True)
    ui_thread.start()

    # The watcher needs a reference to the UI thread to stop it
    watcher_thread = Thread(target=input_watcher, args=(state, ui_thread), daemon=True)
    watcher_thread.start()

    return watcher_thread, ui_thread
