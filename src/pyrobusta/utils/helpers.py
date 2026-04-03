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


def add_method(cls, func, method_type="instance"):
    """
    Helper to patch/extend classes with
    additional methods and states.
    """
    if method_type == "instance":
        setattr(cls, func.__name__, func)
    elif method_type == "static":
        setattr(cls, func.__name__, staticmethod(func))
    elif method_type == "class":
        setattr(cls, func.__name__, classmethod(func))
    else:
        raise ValueError("Invalid type")
