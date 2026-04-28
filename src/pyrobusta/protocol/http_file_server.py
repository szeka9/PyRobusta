"""
State machine extension for file serving.
"""

# pylint: disable=W0212,R0401

from os import stat

from pyrobusta.protocol import http
from pyrobusta.utils.helpers import normalize_path, add_method

CONTENT_TYPES = (
    b"raw",
    b"application/octet-stream",
    b"html",
    b"text/html",
    b"css",
    b"text/css",
    b"js",
    b"application/javascript",
    b"json",
    b"application/json",
    b"ico",
    b"image/x-icon",
    b"jpeg",
    b"image/jpeg",
    b"jpg",
    b"image/jpeg",
    b"png",
    b"image/png",
    b"txt",
    b"text/plain",
    b"gif",
    b"image/gif",
)


def _send_file_st(self, _, file_path: bytes):
    """
    State for returning a file. By default, /www is prepended to the path.
    Alternatively, ready any file from the root when the path starts with /files
    if it is configured in http_served_paths.
    :param file_path: path to the file (unnormalized)
    """
    if self.url == b"/files":
        file_path = "/"
    elif self.url.startswith(b"/files/"):
        file_path = file_path[7:]
    elif self.url == b"/":
        file_path = b"/www/index.html"
    else:
        file_path = b"/www" + file_path

    extension = file_path.rsplit(b".", 1)[-1]
    norm_path = normalize_path(file_path.decode("ascii"))
    is_path_served = self.is_norm_path_served(norm_path)
    if not is_path_served:
        try:
            stat(norm_path)
            self.terminate(403, True)
            return
        except OSError:
            self.terminate(404, True)
            return
    try:
        content_type = self._lookup(CONTENT_TYPES, extension)
    except ValueError:
        content_type = self._lookup(CONTENT_TYPES, b"raw")
    try:
        self.set_response_header(
            b"content-length", str(stat(norm_path)[6]).encode("ascii")
        )
        self.set_response_header(b"content-type", content_type)
        self.terminate(200, True)
        if self.method != self.HEAD:
            self.resp_handler = open(norm_path, "rb")  # pylint: disable=R1732
        return
    except OSError:
        self.terminate(404, True)


def apply_patches():
    """
    Apply patches to class attributes for file serving.
    """

    add_method(http.HttpEngine, _send_file_st)
