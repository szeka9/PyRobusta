"""
Helper methods
"""

from os import getcwd


def normalize_path(path: str):
    """
    Normalize a path string to resolve file and directory paths.
    """
    if not path:
        return ""
    parts = []
    for p in path.split("/"):
        if p in (".", ""):
            continue
        if p == "..":
            if parts:
                parts.pop()
        else:
            parts.append(p)
    normalized = "/".join(parts)
    cwd = getcwd()
    if normalized:
        if cwd.endswith("/"):
            return cwd + normalized
        return cwd + "/" + normalized
    return cwd


def is_norm_path_served(path: str, served_paths: list):
    """
    Returns true if a normalized path is configured to be served.
    :param path: path to check
    :param served_paths: list of paths configured to be served
    """
    parts = path.split("/")
    for i, _ in enumerate(parts):
        current_path = "/".join(parts[: i + 1])
        if not current_path:
            current_path = "/"
        if current_path in served_paths:
            return True
    return False


def is_file_path_valid(file_path: str):
    """
    Returns true if an absolute file path is valid.
    """
    if file_path[0] != "/":
        return False
    segment_start = 1

    while True:
        next_segment = file_path.find("/", segment_start + 1) + 1
        if not next_segment:
            return is_path_segment_valid(file_path[segment_start:])
        if not is_path_segment_valid(file_path[segment_start : next_segment - 1]):
            return False
        segment_start = next_segment


def is_path_segment_valid(filename: str):
    """
    Returns true if a filename is valid.
    """
    if (
        not filename
        or len(filename) > 32
        or not all(
            ("A" <= c <= "Z") or ("a" <= c <= "z") or ("0" <= c <= "9") or c in "._-"
            for c in filename
        )
        or filename in (".", "..")
    ):
        return False
    return True
