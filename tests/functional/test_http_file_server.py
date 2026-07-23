import asyncio
import json

from os import stat

from env_utils import (
    garbage_collect,
    test_assert,
    send_request,
    setup_config,
    start_server,
    fmkdir,
    delete_path,
)

from pyrobusta.utils.config import normalize_path


@garbage_collect
async def test_fs_path_traversal():
    setup_config(files_api_enabled=True, served_paths="/test")
    server = await start_server()
    test_root = normalize_path("/test")
    styles_dir = normalize_path("/test/style")
    fmkdir(test_root)
    fmkdir(styles_dir)

    index_html = normalize_path("/test/index.html")
    styles_css = normalize_path("/test/style/styles.css")

    with open(index_html, "w") as f:
        f.write("<html>PyRobusta Home</html>")
    with open(styles_css, "w") as f:
        f.write("/* This is the main stylesheet */")

    try:
        # Test case
        response = await send_request(
            b"GET /files/test HTTP/1.1\r\n"
            b"Content-Length: 0\r\n"
            b"Connection: close\r\n"
            b"Host: localhost\r\n\r\n"
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

        test_assert(
            f"FS path traversal - JSON chunks received",
            json.loads(response_body_decoded),
            [
                {
                    "path": index_html,
                    "created": str(stat(index_html)[9]),
                    "size": str(stat(index_html)[6]),
                },
                {
                    "path": styles_css,
                    "created": str(stat(styles_css)[9]),
                    "size": str(stat(styles_css)[6]),
                },
            ],
        )
    finally:
        delete_path(test_root)
        await server.terminate()


@garbage_collect
async def test_fs_access_control():
    setup_config(files_api_enabled=True, served_paths="/test/allowed")
    server = await start_server()

    test_root = normalize_path("/test")
    fmkdir(test_root)

    # Index page under /test/allowed -> accepted
    allowed_workdir = normalize_path("/test/allowed")
    allowed_index_html = normalize_path("/test/allowed/index.html")
    fmkdir(allowed_workdir)
    with open(allowed_index_html, "w") as f:
        f.write("<html>PyRobusta Home</html>")

    # Index page under /test/rejected -> rejected
    rejected_workdir = normalize_path("/test/rejected")
    rejected_index_html = normalize_path("/test/rejected/index.html")
    fmkdir(rejected_workdir)
    with open(rejected_index_html, "w") as f:
        f.write("<html>PyRobusta Home</html>")

    try:
        # Case #1: /test/allowed/index.html
        response = await send_request(
            b"GET /files/test/allowed/index.html HTTP/1.1\r\n"
            b"Content-Length: 0\r\n"
            b"Connection: close\r\n"
            b"Host: localhost\r\n\r\n"
        )

        response_body = response.split(b"\r\n\r\n")[1]
        test_assert(
            f"FS access control - index page loaded",
            response_body,
            b"<html>PyRobusta Home</html>",
        )

        # Case #2: /test/rejected/index.html
        response = await send_request(
            b"GET /files/test/rejected/index.html HTTP/1.1\r\n"
            b"Content-Length: 0\r\n"
            b"Connection: close\r\n"
            b"Host: localhost\r\n\r\n"
        )

        test_assert(
            f"FS access control - index page rejected",
            response.startswith(b"HTTP/1.1 403 Forbidden"),
            True,
        )
    finally:
        delete_path(test_root)
        await server.terminate()


@garbage_collect
async def test_bulk_file_upload():
    setup_config(files_api_enabled=True, http_multipart_enabled=True)
    server = await start_server()

    user_data = normalize_path("/www/user_data")
    tmp_dir = normalize_path("/tmp")
    fmkdir(user_data)
    fmkdir(tmp_dir)

    try:
        data = (
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

        response = await send_request(data)
        test_assert(
            "bulk file upload - response status is 201 Created",
            response.startswith(b"HTTP/1.1 201 Created"),
            True,
        )

        # Verify files were saved with correct content
        with open(user_data + "/upload-1.txt", "rb") as f:
            content = f.read()
            test_assert(
                "bulk file upload - file 1 content is correct",
                content,
                b"File 1 content\n",
            )

        with open(user_data + "/upload-2.txt", "rb") as f:
            content = f.read()
            test_assert(
                "bulk file upload - file 2 content is correct",
                content,
                b"File 2 content\n",
            )
    finally:
        delete_path(user_data)
        delete_path(tmp_dir)
        await server.terminate()


@garbage_collect
async def test_chunked_file_upload():
    setup_config(files_api_enabled=True)
    server = await start_server()

    user_data = normalize_path("/www/user_data")
    tmp_dir = normalize_path("/tmp")
    fmkdir(user_data)
    fmkdir(tmp_dir)

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

        response = await send_request(data)
        test_assert(
            f"chunked file upload - response status is 201 Created",
            response.startswith(b"HTTP/1.1 201 Created"),
            True,
        )

        # Verify file was saved with correct content
        with open(user_data + "/upload-1.txt", "rb") as f:
            content = f.read()
            test_assert(
                "chunked file upload - file content is correct",
                content,
                b"File 1 content part 1\nFile 1 content part 2\n",
            )
    finally:
        delete_path(user_data)
        delete_path(tmp_dir)
        await server.terminate()


async def test_main():
    await test_fs_path_traversal()
    await test_fs_access_control()
    await test_bulk_file_upload()
    await test_chunked_file_upload()


asyncio.run(test_main())
