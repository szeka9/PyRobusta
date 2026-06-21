"""
Module for extended file serving features, registered at the /files route.
"""

# pylint: disable=W0212,R0401

from os import stat, listdir, rmdir, remove, rename, mkdir
from json import dumps

from pyrobusta.protocol import http
from pyrobusta.utils.helpers import (
    normalize_path,
    is_norm_path_served,
    is_file_path_valid,
    is_path_segment_valid,
)
from pyrobusta.utils.assets import iterate_fs, FS_ITER_FILE

from ..utils.config import (
    get_config,
    CONF_HTTP_SERVED_PATHS,
)

_UPLOAD_ROOT = normalize_path("/www/user_data")
_TMP_DIR = normalize_path("/tmp")


#################################################
# CRUD methods
#################################################


def fs_retrieve(http_ctx, _):
    """
    State for retrieving a file or a directory structure.
    The http_served_paths configuration controls which files/directories
    can be retrieved.
    """
    target_path = http_ctx.url[len(b"/files") :].decode("ascii")
    norm_path = normalize_path(target_path)
    is_path_served = is_norm_path_served(norm_path, get_config(CONF_HTTP_SERVED_PATHS))

    try:
        if not is_path_served:
            stat(norm_path)
            http_ctx.terminate(403)
            return "text/plain", "Forbidden"

        # Retrieve directory structure
        if stat(norm_path)[0] & 0x4000:
            http_ctx.set_response_header(b"content-type", b"application/json")
            http_ctx.set_response_header(b"transfer-encoding", b"chunked")
            http_ctx.terminate(200)
            http_ctx.resp_handler = _traverse_dir_factory(norm_path)
            return

        # Retrieve file
        try:
            extension = target_path.rsplit(".", 1)[-1]
            content_type = http_ctx._lookup(
                http_ctx.CONTENT_TYPES, extension.encode("ascii")
            )
        except ValueError:
            content_type = http_ctx._lookup(http_ctx.CONTENT_TYPES, b"raw")

        http_ctx.set_response_header(
            b"content-length", str(stat(norm_path)[6]).encode("ascii")
        )
        http_ctx.set_response_header(b"content-type", content_type)
        http_ctx.terminate(200)
        if http_ctx.method != http_ctx.HEAD:
            http_ctx.resp_handler = open(norm_path, "rb")  # pylint: disable=R1732
    except OSError:
        http_ctx.terminate(404)
        return "text/plain", "Not found"


def delete_file(http_ctx, _):
    """
    Route handler for delete operations. The URL path
    must point to the exact file or directory path under _UPLOAD_ROOT.
    Only empty directories can be deleted.
    """

    fs_path = normalize_path(http_ctx.url.decode("ascii")[6:])

    try:
        if not fs_path.startswith(_UPLOAD_ROOT):
            stat(fs_path)
            http_ctx.terminate(403)
            return "text/plain", "Forbidden"

        # Delete directory structure
        if stat(fs_path)[0] & 0x4000:
            if listdir(fs_path):
                http_ctx.terminate(400)
                return "text/plain", "Directory not empty"
            rmdir(fs_path)
            http_ctx.terminate(204)
            return "text/plain", "Deleted"

        # Delete file
        remove(fs_path)
        http_ctx.terminate(204)
        return "text/plain", "Deleted"
    except OSError:
        http_ctx.terminate(404)
        return "text/plain", "Not found"


def upload_file(http_ctx, payload: bytes):
    """
    Route handler for single file uploads, supporting chunked transfer encoding.
    Uploads are saved to _UPLOAD_ROOT, with the name determined by the URL path.
    """
    target_path = http_ctx.url.decode("ascii")[6:]

    if http_ctx.is_multipart() or not is_file_path_valid(target_path):
        http_ctx.terminate(400)
        return "text/plain", "Bad request"

    if not normalize_path(target_path).startswith(_UPLOAD_ROOT):
        http_ctx.terminate(403)
        return "text/plain", "Forbidden"

    try:
        if http_ctx.is_chunked():
            file_name_idx = target_path.rfind("/") + 1
            if not file_name_idx:
                http_ctx.terminate(400)
                return "text/plain", "Bad request"

            tmp_path = _TMP_DIR + "/" + f"{target_path[file_name_idx:]}.{http_ctx.id}"

            if payload:  # Wait for more chunks before setting response status
                with open(tmp_path, "ab") as f:
                    f.write(payload)
                return
            # Last chunk received, finalize upload
            rename(tmp_path, normalize_path(target_path))
        else:
            with open(normalize_path(target_path), "wb") as f:
                f.write(payload)

        http_ctx.terminate(201)
        return "text/plain", "OK"
    except OSError:
        http_ctx.terminate(404)
        return "text/plain", "Not found"


def bulk_upload_file(http_ctx, payload: tuple):
    """
    Route handler for bulk file uploads (Content-Type: multipart/form-data)
    This handler is invoked on every part. Every file is saved to _UPLOAD_ROOT, with
    the name determined by the content disposition header. When two parts specify the
    same file name, the content of the second part is appended to the first part.
    Split files to multiple parts for chunking large files to avoid HTTP 413 errors.
    """
    if not http_ctx.is_multipart():
        http_ctx.terminate(400)
        return "text/plain", "Bad request"

    part_headers, part_body = payload

    try:
        filename = get_filename(part_headers)
    except ValueError:
        http_ctx.terminate(415)
        return "text/plain", "Invalid content disposition"

    if not is_path_segment_valid(filename):
        http_ctx.terminate(400)
        return "text/plain", "Invalid or missing filename"

    # Clean stale partial uploads
    if http_ctx.mp_is_first:
        for file in listdir(_TMP_DIR):
            if file.endswith(f".{http_ctx.id}"):
                remove(_TMP_DIR + "/" + file)

    # TODO: support X-Upload-Directory; pylint: disable=W0511
    target_path = _TMP_DIR + "/" + f"{filename}.{http_ctx.id}"
    with open(target_path, "ab") as f:
        f.write(part_body)

    # Finalize uploads
    if http_ctx.mp_is_last:
        suffix = f".{http_ctx.id}"
        for file in listdir(_TMP_DIR):
            if file.endswith(suffix):
                rename(_TMP_DIR + "/" + file, _UPLOAD_ROOT + "/" + file[: -len(suffix)])

        http_ctx.terminate(201)
        return "text/plain", "OK"


#################################################
# Helper functions
#################################################


def get_filename(part_headers: dict):
    """
    Get filename field from content-disposition headers.
    :param part_headers: headers of an individual part
    """
    cd = part_headers.get("content-disposition", "")
    filename = None

    if cd[: min(max(cd.find(";"), 0), len(cd))].strip() != "form-data":
        raise ValueError()

    f_start = cd.find(";") + 1
    f_end = cd.find(";", f_start)

    while f_start < len(cd):
        f_end = len(cd) if f_end == -1 else f_end
        parameter = cd[f_start:f_end].split("=")
        if len(parameter) == 2 and parameter[0].strip() == "filename":
            filename = parameter[1].strip().strip("'").strip('"')
        f_start = f_end + 1
        f_end = cd.find(";", f_start)

    return filename


def _traverse_dir_factory(path):
    """
    Factory method for creating a response handler closure
    for directory content traversal.
    :param path: normalized path to the directory to traverse
    """

    def _traverse_dir(tx):
        """
        Traverse a directory and produce a JSON-formatted
        response of the directory contents.
        :param tx: response buffer
        """
        tx.write(b"[")
        for i, it in enumerate(iterate_fs(path, FS_ITER_FILE)):
            if i != 0:
                tx.write(b",")

            file_stat = stat(it)
            data = dumps(
                {
                    "path": it,
                    "size": str(file_stat[6]),
                    "created": str(file_stat[9]),
                }
            ).encode("ascii")

            written = 0
            while written < len(data):
                to_write = tx.capacity - tx.size()
                if not to_write:
                    raise BufferError()
                tx.write(data[written : written + to_write])
                written += to_write
                yield False
        tx.write(b"]\r\n")
        yield True

    return _traverse_dir


def setup_directories():
    """
    Set up the required directories for file uploads.
    """
    for http_dir in (_UPLOAD_ROOT, _TMP_DIR):
        base_dir = normalize_path("/")
        sub_dirs = http_dir[len(base_dir) :].lstrip("/")

        for subdir in sub_dirs.split("/"):
            current_dir = base_dir + "/" + subdir
            if not subdir in listdir(base_dir):
                mkdir(current_dir)
            base_dir = current_dir

    for file in listdir(_TMP_DIR):
        remove(_TMP_DIR + "/" + file)


def apply_patches():
    """
    Apply patches to class attributes for file serving.
    """

    http.HttpEngine.deregister("/files/{fs_path:path}", "GET")
    http.HttpEngine.deregister("/files/{fs_path:path}", "DELETE")
    http.HttpEngine.deregister("/files/{fs_path:path}", "PUT")
    http.HttpEngine.deregister("/files", "POST")

    http.HttpEngine.register("/files/{fs_path:path}", fs_retrieve, "GET")
    http.HttpEngine.register("/files/{fs_path:path}", delete_file, "DELETE")
    http.HttpEngine.register("/files/{fs_path:path}", upload_file, "PUT")
    http.HttpEngine.register("/files", bulk_upload_file, "POST")

    setup_directories()
