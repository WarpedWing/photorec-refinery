"""
Provides file and directory utility functions for the PhotoRec Cleaner.

This module includes functions for finding PhotoRec's output directories,
cleaning files within those directories based on extension rules, logging
file operations, and reorganizing the final set of kept files.
"""

import os
import shutil
from math import ceil


def clean_folder(
    folder, state, keep_ext=None, exclude_ext=None, logger=None, prefix="Processing"
):
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
    folder_name = os.path.basename(folder)

    for root, _, files in os.walk(folder):
        if state.cancelled:
            break
        for f in files:
            if state.cancelled:
                break
            files_processed += 1
            activity_message = f"{prefix} {folder_name} ({files_processed} files)"
            state.current_activity = activity_message
            if logger:
                logger(activity_message)

            path = os.path.join(root, f)
            lower_f = f.lower()

            # Determine the primary extension for organization and logging
            primary_ext = os.path.splitext(lower_f)[1][1:] if "." in lower_f else ""

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
                state.total_kept_count += 1
                state.kept_files.setdefault(primary_ext, []).append(path)
                log_action(state, folder_name, f, primary_ext, "kept", path)
                if logger:
                    logger(f"Kept: {f}")
            else:
                try:
                    size = os.path.getsize(path)
                    os.remove(path)
                    state.total_deleted_count += 1
                    state.total_deleted_size += size
                    log_action(
                        state, folder_name, f, primary_ext, "deleted", path, size
                    )
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
    if not state.log_writer:
        return

    if size is None:
        try:
            size = os.path.getsize(path)
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
    for d in os.listdir(base_dir):
        if d.startswith("recup_dir.") and os.path.isdir(os.path.join(base_dir, d)):
            try:
                # Extract number for sorting, e.g., 'recup_dir.10' -> 10
                dir_num = int(d.split(".")[-1])
                dirs.append((dir_num, os.path.join(base_dir, d)))
            except (ValueError, IndexError):
                # Ignore directories that don't match the expected pattern
                continue

    # Sort by the directory number and return just the paths
    return [path for _, path in sorted(dirs)]


def organize_by_type(base_dir, state, batch_size=500):
    """
    Moves kept files into new folders organized by file type and batch size.

    After moving, it deletes the original, now-empty `recup_dir.X` folders.

    Args:
        base_dir (str): The root output directory.
        state (AppState): The shared application state containing the lists of
            kept files.
        batch_size (int): The maximum number of files to place in any one subfolder.
    """
    if not state.kept_files or state.cancelled:
        return

    for ext, paths in state.kept_files.items():
        if state.cancelled:
            break
        type_folder = os.path.join(base_dir, ext)
        os.makedirs(type_folder, exist_ok=True)

        if not paths:
            continue

        num_batches = ceil(len(paths) / batch_size)

        if num_batches <= 1:
            # If there's only one batch, move files directly to the type_folder
            for path in paths:
                if state.cancelled:
                    break
                try:
                    shutil.move(path, type_folder)
                except (shutil.Error, OSError):
                    pass
        else:
            # If multiple batches are needed, create subfolders
            for i, path in enumerate(paths):
                if state.cancelled:
                    break
                batch_num = (i // batch_size) + 1
                subfolder_name = str(batch_num)
                subfolder = os.path.join(type_folder, subfolder_name)
                os.makedirs(subfolder, exist_ok=True)
                try:
                    shutil.move(path, subfolder)
                except (shutil.Error, OSError):
                    pass

    if state.cancelled:
        return

    # Clean up the now-empty recup_dir.* folders
    recup_dirs_to_delete = get_recup_dirs(base_dir)
    for folder in recup_dirs_to_delete:
        if state.cancelled:
            break
        try:
            shutil.rmtree(folder)
        except OSError:
            pass  # If it fails, the folder just remains.


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
    if not os.path.isdir(directory):
        return []

    files_list = []
    for item in os.listdir(directory):
        item_path = os.path.join(directory, item)
        if os.path.isfile(item_path):
            try:
                file_name, file_ext = os.path.splitext(item)
                file_size = os.path.getsize(item_path)
                files_list.append((file_name, file_ext.lstrip("."), file_size))
            except OSError:
                # Ignore files that can't be accessed
                continue
    return files_list
