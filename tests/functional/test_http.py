import asyncio
import ssl
import json
import gc

from os import mkdir, remove, rmdir, stat, listdir

from pyrobusta.server import http_server
from pyrobusta.protocol.http import HttpEngine
from pyrobusta.utils.config import (
    CONF_HTTP_SERVED_PATHS,
    CONF_TLS,
    CONF_LOG_LEVEL,
    _CONFIG_CACHE,
    parse_config,
)
from pyrobusta.utils.helpers import normalize_path

#################################################
# Test helpers
#################################################


def garbage_collect(coroutine):
    async def decorated(*args, **kwargs):
        gc.collect()
        await coroutine(*args, **kwargs)
        gc.collect()

    return decorated


def test_assert(name, actual, expected):
    print(f"Test {name}: ", end="")
    if actual == expected:
        print("OK")
    else:
        print("Fail")
        raise AssertionError(f"{actual} != {expected}")


async def send_request(request, tls=False):
    port = (
        http_server.HttpServer.LISTEN_PORT_HTTPS
        if tls
        else http_server.HttpServer.LISTEN_PORT_HTTP
    )

    ctx = None
    if tls:
        # Disable certificate verification due to self-signed cert
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.verify_mode = ssl.CERT_NONE

    reader, writer = await asyncio.open_connection("127.0.0.1", port, ssl=ctx)
    writer.write(request)
    await writer.drain()

    to_read = True
    response = b""
    while to_read:
        response_part = await reader.read(1024)
        response += response_part
        to_read = len(response_part)
    writer.close()
    return response


def fmkdir(path: str):
    try:
        mkdir(path)
    except OSError:
        pass


def delete_path(path):
    for name in listdir(path):
        if path == "/":
            full = "/" + name
        else:
            full = path + "/" + name

        try:
            remove(full)
        except OSError:
            delete_path(full)
            try:
                rmdir(full)
            except OSError:
                pass


#################################################
# Test driver
#################################################


@HttpEngine.route("/test/simple", "GET")
def simple_callback(http_ctx, _):
    if http_ctx.headers["accept"] == "text/plain":
        return "text/plain", "Test response\n"
    elif http_ctx.headers["accept"] == "application/json":
        return "application/json", '{"response": "Test response"}'
    raise ValueError("Unhandled content-type")


@HttpEngine.route("/test/busy", "POST")
def busy_callback(http_ctx, _):
    http_ctx.terminate(503)
    return "text/plain", "Unavailable"


def create_chunked_app_endpoint(endpoint):
    recv_chunks = []

    @HttpEngine.route(endpoint, "POST")
    def chunked_callback(http_ctx, chunk):
        if not chunk:  # Received terminating chunk
            return "application/json", recv_chunks
        recv_chunks.append(chunk.decode("utf8"))


async def start_server():
    """
    Start an HTTP server as a background task
    """
    server = http_server.HttpServer()
    server_task = asyncio.create_task(server.start_socket_server())
    await asyncio.sleep_ms(100)
    return server, server_task


@garbage_collect
async def test_simple_response(tls_enabled):
    setup_config(tls_enabled=tls_enabled)
    server, server_task = await start_server()

    try:
        # Test: text/plain
        plain_response = await send_request(
            b"GET /test/simple HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Connection: close\r\n"
            b"Accept:text/plain\r\n"
            b"\r\n",
            tls_enabled,
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
        json_response = await send_request(
            b"GET /test/simple HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Connection: close\r\n"
            b"Accept: application/json\r\n"
            b"\r\n",
            tls_enabled,
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
        server_task.cancel()
        await server.terminate()


@garbage_collect
async def test_server_busy():
    setup_config()
    server, server_task = await start_server()

    try:
        plain_response = await send_request(
            b"POST /test/busy HTTP/1.1\r\n"
            b"Connection:close\r\n"
            b"Host: localhost\r\n\r\n"
        )
        test_assert(
            f"response is rejected by busy service with 503",
            b"503 Service Unavailable" in plain_response,
            True,
        )
    finally:
        server_task.cancel()
        await server.terminate()


@garbage_collect
async def test_chunked_transfer_encoding():
    setup_config()
    create_chunked_app_endpoint("/test/chunked")
    server, server_task = await start_server()

    try:
        json_response = await send_request(
            b"POST /test/chunked HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Connection: close\r\n"
            b"Transfer-Encoding: chunked\r\n\r\n"
            b"14\r\nchunking\r\ntest\r\ncase\r\n"
            b"E\r\nchunking\r\ntest\r\n"
            b"8\r\nchunking\r\n"
            b"0\r\n\r\n"
        )
        response_body = json.loads(json_response.split(b"\r\n\r\n")[1])
        test_assert(
            f"chunked transfer encoding - all chunks are received",
            response_body,
            ["chunking\r\ntest\r\ncase", "chunking\r\ntest", "chunking"],
        )
    finally:
        server_task.cancel()
        await server.terminate()


@garbage_collect
async def test_fs_access_control():
    setup_config(served_paths="/www/test/allowed")
    server, server_task = await start_server()
    www_root = normalize_path("/www")
    test_root = normalize_path("/www/test")
    fmkdir(www_root)
    fmkdir(test_root)

    # Index page under /test -> accepted
    allowed_workdir = normalize_path("/www/test/allowed")
    allowed_index_html = normalize_path("/www/test/allowed/index.html")
    fmkdir(allowed_workdir)
    with open(allowed_index_html, "w") as f:
        f.write("<html>PyRobusta Home</html>")

    # Index page under / -> rejected
    rejected_workdir = normalize_path("/www/test/rejected")
    rejected_index_html = normalize_path("/www/test/rejected/index.html")
    fmkdir(rejected_workdir)
    with open(rejected_index_html, "w") as f:
        f.write("<html>PyRobusta Home</html>")

    try:
        # Case #1: /test/allowed/index.html
        response = await send_request(
            b"GET /test/allowed/index.html HTTP/1.1\r\n"
            b"Connection: close\r\n"
            b"Host: localhost\r\n\r\n"
        )

        response_body = response.split(b"\r\n\r\n")[1]
        test_assert(
            f"test FS access control - index page loaded",
            response_body,
            b"<html>PyRobusta Home</html>",
        )

        # Case #2: /test/rejected/index.html
        response = await send_request(
            b"GET /test/rejected/index.html HTTP/1.1\r\n"
            b"Connection: close\r\n"
            b"Host: localhost\r\n\r\n"
        )

        test_assert(
            f"test FS access control - index page rejected",
            response.startswith(b"HTTP/1.1 403 Forbidden"),
            True,
        )
    finally:
        delete_path(test_root)
        server_task.cancel()
        await server.terminate()


@garbage_collect
async def test_fs_path_traversal():
    setup_config(served_paths="/test")
    server, server_task = await start_server()
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
            f"test FS path traversal - JSON chunks received",
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
        server_task.cancel()
        await server.terminate()


@garbage_collect
async def test_keepalive():
    setup_config()
    server, server_task = await start_server()

    try:
        # ----------------------------------
        # Case 1: all requests are processed
        # ----------------------------------
        plain_responses = await send_request(
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
            b"\r\n"
        )

        test_assert(
            f"contains all responses (connection: keep-alive)",
            plain_responses.count(b"HTTP/1.1 200 OK"),
            3,
        )

        # -------------------------------------------------------------------
        # Case 2: close connection after the second request (invalid framing)
        # -------------------------------------------------------------------
        plain_responses = await send_request(
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
            b"\r\n"
        )

        test_assert(
            f"contains two responses (connection: keep-alive, invalid framing)",
            plain_responses.count(b"HTTP/1.1"),
            2,
        )

        # ------------------------------------------------
        # Case 3: close connection after the first request
        # ------------------------------------------------
        plain_response = await send_request(
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
            b"\r\n"
        )

        test_assert(
            f"contains single response (connection: close)",
            plain_response.count(b"HTTP/1.1 200 OK"),
            1,
        )
    finally:
        server_task.cancel()
        await server.terminate()


#################################################
# Test methods
#################################################


def setup_config(tls_enabled=False, served_paths=""):
    http_server.HttpServer.LISTEN_PORT_HTTP = 8080
    http_server.HttpServer.LISTEN_PORT_HTTPS = 4443

    _CONFIG_CACHE[2 * CONF_LOG_LEVEL + 1] = "warning"
    _CONFIG_CACHE[2 * CONF_TLS + 1] = tls_enabled
    _CONFIG_CACHE[2 * CONF_HTTP_SERVED_PATHS + 1] = parse_config(
        CONF_HTTP_SERVED_PATHS, served_paths
    )


def test_registration():
    test_assert(
        "simple endpoint registration",
        simple_callback,
        HttpEngine._get_callback(b"/test/simple", b"GET"),
    )

    test_assert(
        "busy endpoint registration",
        busy_callback,
        HttpEngine._get_callback(b"/test/busy", b"POST"),
    )


def test_main():
    test_registration()
    asyncio.run(test_simple_response(tls_enabled=False))
    asyncio.run(test_simple_response(tls_enabled=True))

    asyncio.run(test_server_busy())
    asyncio.run(test_chunked_transfer_encoding())
    asyncio.run(test_fs_access_control())
    asyncio.run(test_fs_path_traversal())
    asyncio.run(test_keepalive())


test_main()
