from pyrobusta.protocol.http import HttpEngine


def multipart_response(num_responses, part_size):
    i = 0

    def response_generator():
        nonlocal i
        i += 1
        if i > num_responses:
            return None
        return "text/plain", b"X" * part_size

    return response_generator


def multipart_producer(http_ctx, _):
    part_count = int(http_ctx.headers.get("x-part-count", 1))
    part_size = int(http_ctx.headers.get("x-part-size", 1024))
    return "multipart/form-data", multipart_response(part_count, part_size)


def multipart_handler(http_ctx, _):
    if (
        http_ctx.headers.get("content-type", "").startswith("multipart/form-data")
        and http_ctx.mp_is_last
    ):
        return "text/plain", "OK"
    pass  # process part data as needed


def load():
    HttpEngine.register("/test/multipart", multipart_producer, "GET")
    HttpEngine.register("/test/multipart", multipart_handler, "POST")
