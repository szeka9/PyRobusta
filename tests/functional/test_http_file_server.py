import os
import json
import sys

from server import Server, LocalServer, DeviceServer
from utils import (
    test_assert,
    send_request,
)

BOOT_SCRIPT = """
import asyncio
import machine

from pyrobusta import application


async def main():
    await application.run()
    while True:
        await asyncio.sleep(1)

asyncio.run(main())
"""


def test_fs_path_traversal(srv: Server):
    srv.setup_config(http_files_api=True, http_served_paths="/test")

    srv.mkdir("/test")
    srv.mkdir("/test/style")

    index_html = srv.write_file("/test/index.html", "<html>PyRobusta Home</html>")
    styles_css = srv.write_file(
        "/test/style/styles.css", "/* This is the main stylesheet */"
    )

    srv.start(BOOT_SCRIPT)

    try:
        # Test case
        response = send_request(
            srv,
            b"GET /files/test HTTP/1.1\r\n"
            b"Content-Length: 0\r\n"
            b"Connection: close\r\n"
            b"Host: localhost\r\n\r\n",
        )

        # Decode chunked transfer encoding
        response_body = response.split(b"\r\n\r\n")[1]
        response_body_decoded = b""
        start = 0

        while start < len(response_body):
            cursor = response_body.index(b"\r\n", start)
            chunk_size = int(response_body[start:cursor], 16)
            if chunk_size == 0:
                break
            chunk_start = cursor + 2
            chunk_end = chunk_start + chunk_size
            response_body_decoded += response_body[chunk_start:chunk_end]
            start = chunk_end + 2

        json_response = json.loads(response_body_decoded)
        test_assert(
            f"FS path traversal - JSON chunks received",
            set([entry["path"] for entry in json_response]),
            set([index_html, styles_css]),
        )
    finally:
        srv.terminate()
        srv.rmdir("/test")


def test_fs_access_control(srv: Server):
    srv.setup_config(http_files_api=True, http_served_paths="/test/allowed")

    srv.mkdir("/test")

    # Index page under /test/allowed -> accepted
    srv.mkdir("/test/allowed")
    srv.write_file("/test/allowed/index.html", "<html>PyRobusta Home</html>")

    # Index page under /test/rejected -> rejected
    srv.mkdir("/test/rejected")
    srv.write_file("/test/rejected/index.html", "<html>PyRobusta Home</html>")

    srv.start(BOOT_SCRIPT)

    try:
        # Case #1: /test/allowed/index.html
        response = send_request(
            srv,
            b"GET /files/test/allowed/index.html HTTP/1.1\r\n"
            b"Content-Length: 0\r\n"
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
            b"GET /files/test/rejected/index.html HTTP/1.1\r\n"
            b"Content-Length: 0\r\n"
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
        srv.rmdir("/test")


def test_misconfigured_path(srv: Server):
    srv.setup_config(http_files_api=True, http_served_paths="/")

    srv.write_file(
        "/allowed",
        "This file is located under root and is served due to configuration.",
    )
    srv.write_file("/pyrobusta.passwd", "<user-data>")
    srv.write_file("/pyrobusta.roles", "<roles-data>")

    srv.start(BOOT_SCRIPT)

    try:
        # Case #1: /allowed
        # Served due to configuration
        response = send_request(
            srv,
            b"GET /files/allowed HTTP/1.1\r\n"
            b"Content-Length: 0\r\n"
            b"Connection: close\r\n"
            b"Host: localhost\r\n\r\n",
        )

        response_body = response.split(b"\r\n\r\n")[1]
        test_assert(
            f"FS access misconfiguration - test file downloaded from root",
            response_body,
            b"This file is located under root and is served due to configuration.",
        )

        # Case #2: /pyrobusta.env
        # Must be rejected by policy
        response = send_request(
            srv,
            b"GET /files/pyrobusta.env HTTP/1.1\r\n"
            b"Content-Length: 0\r\n"
            b"Connection: close\r\n"
            b"Host: localhost\r\n\r\n",
        )

        test_assert(
            f"FS access misconfiguration - config_file file restricted",
            response.startswith(b"HTTP/1.1 403 Forbidden"),
            True,
        )

        # Case #3: /pyrobusta.passwd
        # Must be rejected by policy
        response = send_request(
            srv,
            b"GET /files/pyrobusta.passwd HTTP/1.1\r\n"
            b"Content-Length: 0\r\n"
            b"Connection: close\r\n"
            b"Host: localhost\r\n\r\n",
        )

        test_assert(
            f"FS access misconfiguration - passwd file restricted",
            response.startswith(b"HTTP/1.1 403 Forbidden"),
            True,
        )

        # Case #4: /pyrobusta.roles
        # Must be rejected by policy
        response = send_request(
            srv,
            b"GET /files/pyrobusta.roles HTTP/1.1\r\n"
            b"Content-Length: 0\r\n"
            b"Connection: close\r\n"
            b"Host: localhost\r\n\r\n",
        )

        test_assert(
            f"FS access misconfiguration - roles file restricted",
            response.startswith(b"HTTP/1.1 403 Forbidden"),
            True,
        )
    finally:
        srv.terminate()


def test_bulk_file_upload(srv: Server):
    srv.setup_config(http_files_api=True, http_multipart=True)

    srv.start(BOOT_SCRIPT)

    try:
        request = (
            # Status line + headers
            b"POST /files HTTP/1.1\r\nHost: localhost\r\n"
            b"Connection:close\r\nUser-Agent: curl/8.5.0\r\nAccept: */*\r\nContent-Length: 384\r\n"
            b"Content-Type: multipart/form-data; boundary=------------------------1ukf3aC3uDA7tUn2xudQXn\r\n\r\n"
            # Body with 2 file parts
            b"--------------------------1ukf3aC3uDA7tUn2xudQXn\r\n"
            b'Content-Disposition: form-data; name="file1"; filename="upload-1.txt"\r\n'
            b"Content-Type: text/plain\r\n\r\n"
            b"File 1 content\n\r\n"
            b"--------------------------1ukf3aC3uDA7tUn2xudQXn\r\n"
            b'Content-Disposition: form-data; name="file2"; filename="upload-2.txt"\r\n'
            b"Content-Type: text/plain\r\n\r\n"
            b"File 2 content\n\r\n"
            b"--------------------------1ukf3aC3uDA7tUn2xudQXn--\r\n"
        )

        response = send_request(srv, request)
        test_assert(
            "bulk file upload - response status is 201 Created",
            response.startswith(b"HTTP/1.1 201 Created"),
            True,
        )

        # Verify files were saved with correct content
        response = send_request(
            srv,
            b"GET /files/www/user_data/upload-1.txt HTTP/1.1\r\n"
            b"Content-Length: 0\r\n"
            b"Connection: close\r\n"
            b"Host: localhost\r\n\r\n",
        ).split(b"\r\n\r\n")[1]

        test_assert(
            "bulk file upload - file 1 content is correct",
            response,
            b"File 1 content\n",
        )

        response = send_request(
            srv,
            b"GET /files/www/user_data/upload-2.txt HTTP/1.1\r\n"
            b"Content-Length: 0\r\n"
            b"Connection: close\r\n"
            b"Host: localhost\r\n\r\n",
        ).split(b"\r\n\r\n")[1]

        test_assert(
            "bulk file upload - file 2 content is correct",
            response,
            b"File 2 content\n",
        )

    finally:
        srv.terminate()
        srv.rmdir("/www/user_data")
        srv.rmdir("/tmp")


def test_chunked_file_upload(srv: Server):
    srv.setup_config(http_files_api=True)

    srv.start(BOOT_SCRIPT)

    try:
        data = (
            # Status line + headers
            b"PUT /files/www/user_data/upload-1.txt HTTP/1.1\r\nHost: localhost\r\n"
            b"Connection:close\r\nUser-Agent: curl/8.5.0\r\nAccept: */*\r\nTransfer-Encoding: chunked\r\n"
            b"Content-Type: application/octet-stream\r\n\r\n"
            # Body with 1 file part sent in 2 chunks
            b"16\r\n"
            b"File 1 content part 1\n\r\n"
            b"16\r\n"
            b"File 1 content part 2\n\r\n"
            b"0\r\n\r\n"
        )

        response = send_request(srv, data)
        test_assert(
            f"chunked file upload - response status is 201 Created",
            response.startswith(b"HTTP/1.1 201 Created"),
            True,
        )

        # Verify file was saved with correct content
        response = send_request(
            srv,
            b"GET /files/www/user_data/upload-1.txt HTTP/1.1\r\n"
            b"Content-Length: 0\r\n"
            b"Connection: close\r\n"
            b"Host: localhost\r\n\r\n",
        ).split(b"\r\n\r\n")[1]

        test_assert(
            "chunked file upload - file content is correct",
            response,
            b"File 1 content part 1\nFile 1 content part 2\n",
        )

    finally:
        srv.terminate()
        srv.rmdir("/www/user_data")
        srv.rmdir("/tmp")


def test_main(srv: Server):
    test_fs_path_traversal(srv)
    test_fs_access_control(srv)
    test_misconfigured_path(srv)
    test_bulk_file_upload(srv)
    test_chunked_file_upload(srv)


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
