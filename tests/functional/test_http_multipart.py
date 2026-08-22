import os
import sys

from server import Server, LocalServer, DeviceServer
from utils import (
    test_assert,
    send_request,
)

BOOT_SCRIPT = """
import asyncio
import machine

from pyrobusta.protocol.http import HttpEngine
from pyrobusta import application


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

async def main():
    await application.run()
    while True:
        await asyncio.sleep(1)

asyncio.run(main())
"""


def test_multipart_response(srv: Server):
    srv.setup_config(http_multipart=True)
    srv.start(BOOT_SCRIPT)

    try:
        # Test: 1 part
        plain_response = send_request(
            srv,
            b"GET /test/multipart HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Length: 0\r\n"
            b"Connection: close\r\n"
            b"X-Part-Count: 1\r\n\r\n",
        )

        test_assert(
            f"multipart response contains 1 part",
            b"Response 1" in plain_response,
            True,
        )

        # Test: 10 parts
        plain_response = send_request(
            srv,
            b"GET /test/multipart HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Length: 0\r\n"
            b"Connection: close\r\n"
            b"X-Part-Count: 10\r\n\r\n",
        )

        test_assert(
            f"multipart response contains 10 parts",
            [b"Response %d" % i in plain_response for i in range(1, 11)],
            [True] * 10,
        )
    finally:
        srv.terminate()


def test_main(srv: Server):
    test_multipart_response(srv)


if __name__ == "__main__":
    server_ip = sys.argv[1]
    server_id = sys.argv[
        2
    ]  # mpremote id e.g. a1 (/dev/ttyACM1), or 'local' for the unix port

    if server_id == "local":
        srv = LocalServer(server_ip, os.getcwd(), os.getenv("MICROPYTHON"))
    else:
        srv = DeviceServer(server_ip, server_id)

    test_main(srv)
