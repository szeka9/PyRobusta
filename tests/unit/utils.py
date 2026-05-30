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


def stat_factory(is_file):
    def fake_stat(_):
        st_mode = 0o100000 | 0o644 if is_file else 0o040000 | 0o755
        return os.stat_result(
            (
                st_mode,  # st_mode
                12345678,  # st_ino
                2049,  # st_dev
                1,  # st_nlink
                1000,  # st_uid
                1000,  # st_gid
                1024,  # st_size
                int(time.time()),  # st_atime
                int(time.time()),  # st_mtime
                int(time.time()),  # st_ctime
            )
        )

    return fake_stat
