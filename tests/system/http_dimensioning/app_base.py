from pyrobusta.protocol.http import HttpEngine


def chunk_handler(_, chunk):
    if not chunk:  # Received terminating chunk/part
        return "text/plain", "OK"
    pass  # process chunk data as needed


def load():
    HttpEngine.register("/test/stream", chunk_handler, "POST")
