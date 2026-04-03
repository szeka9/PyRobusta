"""
State machine extension for file serving.
"""

# pylint: disable=W0212,R0401

from os import stat

from pyrobusta.protocol import http
from pyrobusta.utils.helpers import normalize_path, add_method


def _send_file_st(self, _, tx, web_resource: bytes):
    """State for returning a static resource"""
    if self.url == b"/files":
        web_resource = "/"
    elif self.url.startswith(b"/files/"):
        web_resource = web_resource[7:]
    elif self.url == b"/":
        web_resource = b"/www/index.html"
    else:
        web_resource = b"/www" + web_resource

    extension = web_resource.rsplit(b".", 1)[-1]
    norm_path = normalize_path(web_resource.decode(self.ASCII))
    is_path_served = self.is_norm_path_served(norm_path)
    if not is_path_served:
        try:
            stat(norm_path)
            self.on_forbidden(tx)
            return
        except OSError:
            self.on_missing_resource(tx)
            return
    try:
        content_type = self._lookup(self.CONTENT_TYPES, extension)
    except ValueError:
        content_type = self._lookup(self.CONTENT_TYPES, b"raw")
    try:
        self._set_response_header(
            b"content-length", str(stat(norm_path)[6]).encode(http.HttpEngine.ASCII)
        )
        self.terminate(200, content_type)
        self._write_response_head(tx, None)
        if self.method != self.HEAD:
            return open(norm_path, "rb")
        return
    except OSError:
        self.on_missing_resource(tx)


def apply_patches():
    """
    Apply patches to class attributes for file serving.
    """

    add_method(http.HttpEngine, _send_file_st)
