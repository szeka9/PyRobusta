"""
Helper methods for lexical path handling.
"""

import pyrobusta


def iterate_segments(data: str, delimiter: str):
    """
    Generator for iterating over each segment of a string,
    separated by an arbitrary delimiter. The generator
    does not ignore empty segments (including leading and
    trailing segments).
    """
    start = 0
    end = 0
    while start < len(data):
        end = data.find(delimiter, start)
        if end == -1:
            end = len(data)
        yield data[start:end].strip()
        start = end + 1
    if data.endswith(delimiter):
        yield ""


def normalize_path(path: str):
    """
    Normalize a path string to resolve file and directory paths.
    """
    if not path:
        return ""
    parts = []
    for p in iterate_segments(path, "/"):
        if p == "." or not p:
            continue
        if p == "..":
            if parts:
                parts.pop()
        else:
            parts.append(p)
    normalized = "/".join(parts)
    if normalized:
        return pyrobusta.WORKING_DIR + "/" + normalized
    if not pyrobusta.WORKING_DIR:
        return "/"
    return pyrobusta.WORKING_DIR


def is_child_path_of(path: str, parent_paths):
    """
    Returns true if a normalized path is the child of a parent path.
    :param path: path to check
    :param parent_paths: parent paths to check against
    """
    if not path:
        return "/" in parent_paths
    pos = 0
    while True:
        pos = path.find("/", pos)
        if pos < 0:
            return path in parent_paths
        current_path = path[:pos] or "/"
        if current_path in parent_paths:
            return True
        pos += 1


def is_file_path_valid(file_path: str):
    """
    Returns true if an absolute file path is valid.
    """
    if file_path[0] != "/" or file_path == "/":
        return False
    for segment in iterate_segments(file_path[1:], "/"):
        if not is_path_segment_valid(segment):
            return False
    return True


def is_path_segment_valid(filename: str):
    """
    Returns true if a filename is valid.
    """
    if not filename or len(filename) > 32:
        return False

    if filename == "." or filename == "..":
        return False

    for c in filename:
        if not (
            ("A" <= c <= "Z")
            or ("a" <= c <= "z")
            or ("0" <= c <= "9")
            or c == "."
            or c == "_"
            or c == "-"
        ):
            return False

    return True
