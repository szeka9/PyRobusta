"""
Helper functions to install assets.
"""

from os import mkdir, listdir, stat

from .helpers import normalize_path

FS_ITER_ABS = 0
FS_ITER_REL = 1

FS_ITER_FILE = 0
FS_ITER_DIR = 1


def copy_file(src_path, dst_path):
    """
    Copy a file from a to a destination path.
    """
    with open(src_path, "rb") as src:
        with open(dst_path, "wb") as dst:
            while True:
                chunk = src.read(512)
                if not chunk:
                    break
                dst.write(chunk)


def iterate_fs(root, iter_mode=FS_ITER_FILE, path_mode=FS_ITER_ABS):
    """
    Iterate over all files or directories and yield
    resulting paths either as absolute or relative paths.
    :param dir: directory in which to iterate
    :iter_mode int: iterate over files (FS_ITER_FILE=0) or directories (FS_ITER_DIR=1)
    :path_mode int: yield absolute paths (FS_ITER_ABS=0) ro relative paths (FS_ITER_REL=1)
    """
    dirs = [root]
    while dirs:
        current_directory = dirs.pop(0)
        for name in listdir(current_directory):
            if current_directory == "/":
                current_path = "/" + name
            else:
                current_path = current_directory + "/" + name
            st = stat(current_path)
            fs_mode = st[0]
            if fs_mode & 0x4000:  # directory bit set
                dirs.append(current_path)
                if iter_mode == FS_ITER_DIR:
                    if path_mode == FS_ITER_REL:
                        yield current_path[len(root) + 1 :]
                    else:
                        yield current_path
                else:
                    continue
            if iter_mode == FS_ITER_FILE:
                if path_mode == FS_ITER_REL:
                    yield current_path[len(root) + 1 :]
                else:
                    yield current_path


def install_www():
    """
    Install default web server assets under /www.
    """
    source_dir = normalize_path("/lib/pyrobusta/assets/www")
    target_dir = normalize_path("/www")
    if "www" not in listdir():
        mkdir(target_dir)

    for asset_dir in iterate_fs(source_dir, FS_ITER_DIR, FS_ITER_ABS):
        mkdir(asset_dir)

    for asset in iterate_fs(source_dir, FS_ITER_FILE, FS_ITER_REL):
        copy_file(
            source_dir + "/" + asset,
            target_dir + "/" + asset,
        )
