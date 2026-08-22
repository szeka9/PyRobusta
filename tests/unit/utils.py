"""
Utility scripts used by unit tests.
"""

import sys
import importlib.util
import time
import os
import types
from pathlib import Path


def load_module(relative_path):
    """
    Load a Python module from src/ under its normal package name.
    The module is registered in sys.modules before execution so
    subsequent imports resolve to the same fresh instance and see
    test monkey-patches. Each call replaces any existing module
    with the same name.
    """
    src_root = Path(__file__).resolve().parent.parent.parent / "src"
    src_root = src_root.resolve()

    full_path = (src_root / relative_path).resolve()

    # Prevent paths outside src/ from being loaded accidentally.
    try:
        relative = full_path.relative_to(src_root)
    except ValueError as exc:
        raise ValueError(
            f"Module path is outside source root: {relative_path!r}"
        ) from exc

    if not full_path.is_file():
        raise FileNotFoundError(f"Module file does not exist: {full_path}")

    if full_path.suffix != ".py":
        raise ValueError(f"Expected a Python source file, got: {full_path}")

    # Ensure normal imports can resolve the source tree.
    src_root_str = str(src_root)
    if src_root_str not in sys.path:
        sys.path.insert(0, src_root_str)

    module_name = ".".join(relative.with_suffix("").parts)

    spec = importlib.util.spec_from_file_location(
        module_name,
        full_path,
    )

    if spec is None:
        raise ImportError(f"Could not create import spec for {full_path}")

    if spec.loader is None:
        raise ImportError(f"Module spec has no loader for {full_path}")

    module = importlib.util.module_from_spec(spec)

    # Register before executing the module.
    sys.modules[module_name] = module

    try:
        spec.loader.exec_module(module)
    except BaseException:
        # Do not leave a partially initialized module behind.
        if sys.modules.get(module_name) is module:
            del sys.modules[module_name]
        raise

    return module


def patch_time():
    time_module = types.ModuleType("time")

    time_module.ticks_ms = lambda: time.monotonic_ns() // 1_000_000
    time_module.ticks_add = lambda ticks, ms: ticks + ms
    time_module.ticks_diff = lambda ticks1, ticks2: ticks1 - ticks2

    sys.modules["time"] = time_module


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
