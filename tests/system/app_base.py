# pylint: disable=E0401
from pyrobusta.protocol.http import HttpEngine


def chunk_handler(_, chunk: bytes):
    if not chunk:  # Received terminating chunk/part
        return "text/plain", "OK"
    # <process chunk data>
    return None


def load():
    HttpEngine.register("/test/stream", chunk_handler, "POST")
