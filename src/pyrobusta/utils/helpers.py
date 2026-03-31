"""
Helper methods
"""

from os import getcwd


def normalize_path(path: str):
    """Normalize a path string to resolve file and directory paths"""
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
