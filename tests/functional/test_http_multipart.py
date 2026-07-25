import asyncio

from env_utils import (
    garbage_collect,
    test_assert,
    send_request,
    setup_config,
    start_server,
)

from pyrobusta.protocol import http_multipart
from pyrobusta.protocol.http import HttpEngine


def multipart_response(num_responses):
    i = 0

    def response_generator():
        nonlocal i
        i += 1
        if i > num_responses:
            return None
        return "text/plain", b"Response %s" % i

    return response_generator


@HttpEngine.route("/test/multipart", "GET")
def multipart_handler(http_ctx, _):
    part_count = int(http_ctx.headers["x-part-count"])
    return "multipart/form-data", multipart_response(part_count)


@garbage_collect
async def test_multipart_response():
    setup_config(http_multipart_enabled=True)
    server = await start_server()

    # Test: 1 part
    plain_response = await send_request(
        b"GET /test/multipart HTTP/1.1\r\n"
        b"Host: localhost\r\n"
        b"Content-Length: 0\r\n"
        b"Connection: close\r\n"
        b"X-Part-Count: 1\r\n\r\n"
    )

    test_assert(
        f"multipart response contains 1 part",
        b"Response 1" in plain_response,
        True,
    )

    # Test: 10 parts
    plain_response = await send_request(
        b"GET /test/multipart HTTP/1.1\r\n"
        b"Host: localhost\r\n"
        b"Content-Length: 0\r\n"
        b"Connection: close\r\n"
        b"X-Part-Count: 10\r\n\r\n"
    )

    test_assert(
        f"multipart response contains 10 parts",
        [b"Response %s" % i in plain_response for i in range(1, 11)],
        [True] * 10,
    )

    await server.terminate()


def test_registration():
    test_assert(
        "multipart route registration",
        multipart_handler,
        HttpEngine._get_handler(b"/test/multipart", b"GET"),
    )


def test_multipart_patches():
    setup_config(http_multipart_enabled=True)
    test_assert(
        "multipart state machine patches",
        http_multipart._start_multipart_parser_st,
        HttpEngine._start_multipart_parser_st,
    )


async def test_main():
    test_registration()
    test_multipart_patches()
    await test_multipart_response()


asyncio.run(test_main())
