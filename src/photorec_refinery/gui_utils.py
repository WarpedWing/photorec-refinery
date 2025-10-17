"""
Utility functions for the PhotoRec Cleaner GUI.
"""

MAX_STATUS_PATH = 80


def shorten_path(path: str, maxlen: int = MAX_STATUS_PATH) -> str:
    if not path:
        return ""
    if len(path) <= maxlen:
        return path
    head = path[: maxlen // 2 - 2]
    tail = path[-(maxlen // 2 - 1) :]
    return f"{head}...{tail}"


def tail_truncate(text: str, maxlen: int = MAX_STATUS_PATH) -> str:
    """Truncate from the left so the end of the string is visible."""
    if not text:
        return ""
    if len(text) <= maxlen:
        return text
    if maxlen <= 3:
        return text[-maxlen:]
    return "..." + text[-(maxlen - 3) :]
