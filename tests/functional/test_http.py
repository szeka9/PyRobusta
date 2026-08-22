import os
import json
import sys

from server import Server, LocalServer, DeviceServer

from utils import test_assert, send_request

BOOT_SCRIPT = """
import asyncio
import machine

from pyrobusta.protocol.http import HttpEngine
from pyrobusta import application


@HttpEngine.route("/test/simple", "GET")
def simple_handler(http_ctx, _):
    if http_ctx.headers["accept"] == "text/plain":
        return "text/plain", "Test response"
    elif http_ctx.headers["accept"] == "application/json":
        return "application/json", '{"response": "Test response"}'
    raise ValueError("Unhandled content-type")


@HttpEngine.route("/test/busy", "POST")
def busy_handler(http_ctx, _):
    http_ctx.terminate(503)
    return "text/plain", "Unavailable"

recv_chunks = []

@HttpEngine.route("/test/chunked", "POST")
def chunked_handler(http_ctx, chunk):
    global recv_chunks
    if not chunk:  # Received terminating chunk
        return "application/json", recv_chunks
    recv_chunks.append(chunk.decode("utf8"))

async def main():
    await application.run()
    while True:
        await asyncio.sleep(1)

asyncio.run(main())
"""


def test_simple_response(srv: Server, tls_enabled):
    srv.setup_config(tls=tls_enabled)
    srv.start(BOOT_SCRIPT)

    try:
        # Test: text/plain
        plain_response = send_request(
            srv,
            b"GET /test/simple HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Connection: close\r\n"
            b"Accept:text/plain\r\n"
            b"\r\n",
        )
        test_assert(
            f"http{"s" if tls_enabled else ""} response contains text/plain header",
            b"text/plain" in plain_response,
            True,
        )
        test_assert(
            f"http{"s" if tls_enabled else ""} response contains text/plain body",
            b"Test response" in plain_response,
            True,
        )

        # Test: application/json
        json_response = send_request(
            srv,
            b"GET /test/simple HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Connection: close\r\n"
            b"Accept: application/json\r\n"
            b"\r\n",
        )
        test_assert(
            f"http{"s" if tls_enabled else ""} response contains application/json header",
            b"application/json" in json_response,
            True,
        )
        test_assert(
            f"http{"s" if tls_enabled else ""} response contains application/json body",
            b'{"response": "Test response"}' in json_response,
            True,
        )
    finally:
        srv.terminate()


def test_server_busy(srv: Server):
    srv.setup_config()
    srv.start(BOOT_SCRIPT)

    try:
        plain_response = send_request(
            srv,
            b"POST /test/busy HTTP/1.1\r\n"
            b"Connection:close\r\n"
            b"Host: localhost\r\n\r\n",
        )
        test_assert(
            f"response is rejected by busy service with 503",
            b"503 Service Unavailable" in plain_response,
            True,
        )
    finally:
        srv.terminate()


def test_chunked_transfer_encoding(srv: Server):
    srv.setup_config()
    srv.start(BOOT_SCRIPT)

    try:
        json_response = send_request(
            srv,
            b"POST /test/chunked HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Connection: close\r\n"
            b"Transfer-Encoding: chunked\r\n\r\n"
            b"14\r\nchunking\r\ntest\r\ncase\r\n"
            b"E\r\nchunking\r\ntest\r\n"
            b"8\r\nchunking\r\n"
            b"0\r\n\r\n",
        )
        response_body = json.loads(json_response.split(b"\r\n\r\n")[1])
        test_assert(
            f"chunked transfer encoding - all chunks are received",
            response_body,
            ["chunking\r\ntest\r\ncase", "chunking\r\ntest", "chunking"],
        )
    finally:
        srv.terminate()


def test_fs_access_control(srv: Server):
    srv.setup_config(http_served_paths="/www/test/allowed")

    srv.mkdir("/www/test")

    # Index page under /test/allowed -> accepted
    srv.mkdir("/www/test/allowed")
    srv.write_file("/www/test/allowed/index.html", "<html>PyRobusta Home</html>")

    # Index page under /test/rejected -> rejected
    srv.mkdir("/www/test/rejected")
    srv.write_file("/www/test/rejected/index.html", "<html>PyRobusta Home</html>")

    srv.start(BOOT_SCRIPT)

    try:
        # Case #1: /test/allowed/index.html
        response = send_request(
            srv,
            b"GET /test/allowed/index.html HTTP/1.1\r\n"
            b"Connection: close\r\n"
            b"Host: localhost\r\n\r\n",
        )

        response_body = response.split(b"\r\n\r\n")[1]
        test_assert(
            f"FS access control - index page loaded",
            response_body,
            b"<html>PyRobusta Home</html>",
        )

        # Case #2: /test/rejected/index.html
        response = send_request(
            srv,
            b"GET /test/rejected/index.html HTTP/1.1\r\n"
            b"Connection: close\r\n"
            b"Host: localhost\r\n\r\n",
        )

        test_assert(
            f"FS access control - index page rejected",
            response.startswith(b"HTTP/1.1 403 Forbidden"),
            True,
        )
    finally:
        srv.terminate()
        srv.rmdir("/www/test")


def test_keepalive(srv: Server):
    srv.setup_config()
    srv.start(BOOT_SCRIPT)

    try:
        # ----------------------------------
        # Case 1: all requests are processed
        # ----------------------------------
        plain_responses = send_request(
            srv,
            b"GET /test/simple HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Accept:text/plain\r\n"
            b"\r\n"
            b"GET /test/simple HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Accept:text/plain\r\n"
            b"\r\n"
            b"GET /test/simple HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Connection: close\r\n"
            b"Accept:text/plain\r\n"
            b"\r\n",
        )

        test_assert(
            f"contains all responses (connection: keep-alive)",
            plain_responses.count(b"HTTP/1.1 200 OK"),
            3,
        )

        # -------------------------------------------------------------------
        # Case 2: close connection after the second request (invalid framing)
        # -------------------------------------------------------------------
        plain_responses = send_request(
            srv,
            b"GET /test/simple HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Accept:text/plain\r\n"
            b"\r\n"
            b"GET /test/simple HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"<INVALID HEADER>"
            b"Accept:text/plain\r\n"
            b"\r\n"
            b"GET /test/simple HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Accept:text/plain\r\n"
            b"\r\n",
        )

        test_assert(
            f"contains two responses (connection: keep-alive, invalid framing)",
            plain_responses.count(b"HTTP/1.1"),
            2,
        )

        # ------------------------------------------------
        # Case 3: close connection after the first request
        # ------------------------------------------------
        plain_response = send_request(
            srv,
            b"GET /test/simple HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Connection: close\r\n"
            b"Accept:text/plain\r\n"
            b"\r\n"
            b"GET /test/simple HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Accept:text/plain\r\n"
            b"\r\n"
            b"GET /test/simple HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Accept:text/plain\r\n"
            b"\r\n",
        )

        test_assert(
            f"contains single response (connection: close)",
            plain_response.count(b"HTTP/1.1 200 OK"),
            1,
        )
    finally:
        srv.terminate()


def test_main(srv: Server):
    test_simple_response(srv, tls_enabled=False)
    test_simple_response(srv, tls_enabled=True)
    test_server_busy(srv)
    test_chunked_transfer_encoding(srv)
    test_fs_access_control(srv)
    test_keepalive(srv)


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
