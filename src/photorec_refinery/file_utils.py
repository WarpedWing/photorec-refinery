"""
Provides file and directory utility functions for the PhotoRec Cleaner.

This module includes functions for finding PhotoRec's output directories,
cleaning files within those directories based on extension rules, logging
file operations, and reorganizing the final set of kept files.
"""

import contextlib
import os
import shutil
from pathlib import Path


class OperationCancelled(Exception):
    """Signal to abort the current operation immediately."""

    pass


def clean_folder(folder, state, keep_ext=None, exclude_ext=None, logger=None, prefix="Processing"):
    """
    Walks through a folder, deleting or keeping files based on extension rules.

    This function iterates through all files in the given folder and its
    subdirectories. It updates the shared `state` object with counts and sizes
    of deleted/kept files and logs actions if logging is enabled.

    Args:
        folder (str): The path to the folder to clean.
        state (AppState): The shared application state object.
        keep_ext (set, optional): A set of file extensions to keep.
        exclude_ext (set, optional): A set of file extensions to explicitly delete.
            This takes precedence over `keep_ext`.
        logger (function, optional): A callback function for logging messages.
        prefix (str, optional): A string to prepend to activity log messages.
    """
    files_processed = 0
    folder_path = Path(folder)
    folder_name = folder_path.name

    for root, _, files in os.walk(folder):
        if state.cancelled:
            raise OperationCancelled()
        root_path = Path(root)
        for f in files:
            if state.cancelled:
                raise OperationCancelled()
            files_processed += 1
            activity_message = f"{prefix} {folder_name} ({files_processed} files)"
            state.current_activity = activity_message
            if logger:
                logger(activity_message)

            path = root_path / f
            lower_f = f.lower()

            # Determine the primary extension for organization and logging
            # Extensionless files go to "unknown" folder
            primary_ext = Path(lower_f).suffix[1:] if "." in lower_f else "unknown"

            # Keep SQLite associated files (.shm, .wal, .journal) with their parent
            if any(lower_f.endswith(f".sqlite-{ext}") for ext in ("shm", "wal", "journal")):
                primary_ext = "sqlite"

            # Default to keeping the file if no keep rules are specified.
            # If keep_ext is a non-empty set, default to deleting.
            keep = not keep_ext

            # Check keep rules first.
            if keep_ext:
                for ext in keep_ext:
                    if lower_f.endswith("." + ext):
                        keep = True
                        primary_ext = ext  # Use the matched extension
                        break

            # Exclusion rules override any keep rules.
            if exclude_ext:
                for ext in exclude_ext:
                    if lower_f.endswith("." + ext):
                        keep = False
                        primary_ext = ext  # Use the matched extension
                        break

            if keep:
                if state.cancelled:
                    raise OperationCancelled()
                state.total_kept_count += 1
                state.kept_files.setdefault(primary_ext, []).append(str(path))
                log_action(state, folder_name, f, primary_ext, "kept", str(path))
                if logger:
                    logger(f"Kept: {f}")
            else:
                if state.cancelled:
                    raise OperationCancelled()
                try:
                    size = path.stat().st_size
                    path.unlink()
                    state.total_deleted_count += 1
                    state.total_deleted_size += size
                    log_action(state, folder_name, f, primary_ext, "deleted", str(path), size)
                    if logger:
                        logger(f"Deleted: {f}")
                except OSError:
                    # We could log this to a file if needed, but for the UI, we just continue.
                    pass


def log_action(state, folder, filename, ext, status, path, size=None):
    """
    Writes a record of a file operation to the CSV log file if enabled.

    Args:
        state (AppState): The shared application state object.
        folder (str): The base name of the `recup_dir` folder.
        filename (str): The name of the file being processed.
        ext (str): The file's extension.
        status (str): The action taken ("kept" or "deleted").
        path (str): The full path to the file.
        size (int, optional): The file size. If not provided, it will be
            calculated. Defaults to None.
    """
    if state.cancelled or not state.log_writer:
        return

    if size is None:
        try:
            size = Path(path).stat().st_size
        except OSError:
            size = -1

    state.log_writer.writerow([folder, filename, ext, status, size])


def get_recup_dirs(base_dir):
    """
    Finds all `recup_dir.X` directories and sorts them numerically.

    This ensures that `recup_dir.10` comes after `recup_dir.9`.

    Args:
        base_dir (str): The directory to search in.

    Returns:
        list: A sorted list of full paths to the `recup_dir` directories.
    """
    dirs = []
    base_path = Path(base_dir)
    for d in base_path.iterdir():
        if d.name.startswith("recup_dir.") and d.is_dir():
            try:
                # Extract number for sorting, e.g., 'recup_dir.10' -> 10
                dir_num = int(d.name.split(".")[-1])
                dirs.append((dir_num, str(d)))
            except (ValueError, IndexError):
                # Ignore directories that don't match the expected pattern
                continue

    # Sort by the directory number and return just the paths
    return [path for _, path in sorted(dirs)]


def organize_by_type(base_dir, state, batch_size=500, progress_cb=None):
    """
    Moves kept files into new folders organized by file type and batch size.

    After moving, it deletes the original, now-empty `recup_dir.X` folders.

    Args:
        base_dir (str): The root output directory.
        state (AppState): The shared application state containing the lists of
            kept files.
        batch_size (int): The maximum number of files to place in any one subfolder.
    """
    if state.cancelled:
        raise OperationCancelled()
    if not state.kept_files:
        return

    base_path = Path(base_dir)

    # Determine total moves for progress reporting
    total_to_move = 0
    if state.kept_files:
        try:
            total_to_move = sum(len(paths or []) for paths in state.kept_files.values())
        except Exception:
            total_to_move = 0
    moved_overall = 0
    if progress_cb and total_to_move > 0:
        with contextlib.suppress(Exception):
            progress_cb(0, total_to_move)

    # Move PhotoRec's carve report.xml to root directory instead of xml folder
    if "xml" in state.kept_files:
        xml_paths = state.kept_files["xml"]
        paths_to_remove = []
        for path in xml_paths:
            if Path(path).name.lower() == "report.xml":
                # Check if it's PhotoRec's carve report
                try:
                    with Path(path).open(encoding="utf-8") as f:
                        content = f.read(1024)  # Read first 1KB
                        if "<dc:type>Carve Report</dc:type>" in content:
                            shutil.move(path, base_path)
                            moved_overall += 1
                            if progress_cb and total_to_move > 0:
                                with contextlib.suppress(Exception):
                                    progress_cb(moved_overall, total_to_move)
                            paths_to_remove.append(path)
                except (OSError, UnicodeDecodeError):
                    pass  # Skip if can't read or move
        # Remove processed paths from xml list
        for path in paths_to_remove:
            xml_paths.remove(path)

    for ext, paths in state.kept_files.items():
        if state.cancelled:
            raise OperationCancelled()
        type_folder = base_path / ext
        type_folder.mkdir(exist_ok=True)

        if not paths:
            continue

        use_subfolders = len(paths) > batch_size
        moved = 0
        for path in paths:
            if state.cancelled:
                raise OperationCancelled()
            # Determine destination based on successfully moved count
            if use_subfolders:
                batch_num = (moved // batch_size) + 1
                dest = type_folder / str(batch_num)
                dest.mkdir(exist_ok=True)
            else:
                dest = type_folder
            try:
                shutil.move(path, dest)
                moved += 1
                moved_overall += 1
                if progress_cb and total_to_move > 0:
                    with contextlib.suppress(Exception):
                        progress_cb(moved_overall, total_to_move)
            except (shutil.Error, OSError):
                # Skip files that can't be moved; don't advance batch counter
                continue

    if state.cancelled:
        raise OperationCancelled()

    # Clean up the now-empty recup_dir.* folders
    recup_dirs_to_delete = get_recup_dirs(base_dir)
    for folder in recup_dirs_to_delete:
        if state.cancelled:
            raise OperationCancelled()
        with contextlib.suppress(OSError):
            shutil.rmtree(folder)


def get_files_in_directory(directory):
    """
    Lists all files in a given directory, returning their details.

    Args:
        directory (str): The absolute path to the directory.

    Returns:
        list: A list of tuples, where each tuple contains:
              (file_name, extension, size_in_bytes).
              Returns an empty list if the directory is not valid.
    """
    dir_path = Path(directory)
    if not dir_path.is_dir():
        return []

    files_list = []
    for item in dir_path.iterdir():
        if item.is_file():
            try:
                file_name = item.stem
                file_ext = item.suffix.lstrip(".")
                file_size = item.stat().st_size
                files_list.append((file_name, file_ext, file_size))
            except OSError:
                # Ignore files that can't be accessed
                continue
    return files_list
