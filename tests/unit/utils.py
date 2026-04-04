"""
Utility scripts used by unit tests.
"""

import sys
import importlib.util
import time
import os
from pathlib import Path


def load_module(relative_path):
    """
    Resolve and create a module from a path.
    """
    here = Path(__file__).resolve()
    src_root = here.parent.parent.parent / "src"

    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))

    full_path = (src_root / relative_path).resolve()
    rel = full_path.relative_to(src_root)
    module_name = ".".join(rel.with_suffix("").parts)
    spec = importlib.util.spec_from_file_location(module_name, str(full_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def fake_stat(size=1024):
    return os.stat_result(
        (
            0o100644,  # st_mode (regular file, 644 perms)
            12345678,  # st_ino
            2049,  # st_dev
            1,  # st_nlink
            1000,  # st_uid
            1000,  # st_gid
            size,  # st_size
            int(time.time()),  # st_atime
            int(time.time()),  # st_mtime
            int(time.time()),  # st_ctime
        )
    )
