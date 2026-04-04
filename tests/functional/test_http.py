import asyncio
import ssl
import json
import gc

from os import mkdir, remove, rmdir

from pyrobusta.server import http_server
from pyrobusta.protocol.http import (
    HttpEngine,
    enable_optional_features,
    ServerBusyError,
)
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
def busy_callback(*_):
    raise ServerBusyError()


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

    # Test: text/plain
    plain_response = await send_request(
        b"GET /test/simple HTTP/1.1\r\n"
        b"Host: localhost\r\nAccept:text/plain\r\n"
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
        b"Host: localhost\r\nAccept:application/json\r\n"
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

    server_task.cancel()
    await server.terminate()


@garbage_collect
async def test_server_busy():
    setup_config()
    server, server_task = await start_server()

    plain_response = await send_request(
        b"POST /test/busy HTTP/1.1\r\n" b"Host: localhost\r\n\r\n"
    )
    test_assert(
        f"response is rejected by busy service with 503",
        b"503 Service Unavailable" in plain_response,
        True,
    )

    server_task.cancel()
    await server.terminate()


@garbage_collect
async def test_chunked_transfer_encoding():
    setup_config()
    create_chunked_app_endpoint("/test/chunked")
    server, server_task = await start_server()

    json_response = await send_request(
        (
            b"POST /test/chunked HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Transfer-Encoding: chunked\r\n\r\n"
            b"14\r\nchunking\r\ntest\r\ncase\r\n"
            b"E\r\nchunking\r\ntest\r\n"
            b"8\r\nchunking\r\n"
            b"0\r\n\r\n"
        )
    )
    response_body = json.loads(json_response.split(b"\r\n\r\n")[1])
    test_assert(
        f"chunked transfer encoding - all chunks are received",
        response_body,
        ["chunking\r\ntest\r\ncase", "chunking\r\ntest", "chunking"],
    )

    server_task.cancel()
    await server.terminate()


@garbage_collect
async def test_fs_access_control():
    setup_config(served_paths="/www/allowed")
    server, server_task = await start_server()
    workdir_root = normalize_path("/www")
    try:
        mkdir(workdir_root)
    except:
        pass

    # Index page under /www -> accepted
    allowed_workdir = normalize_path("/www/allowed")
    allowed_index_html = normalize_path("/www/allowed/index.html")
    mkdir(allowed_workdir)
    with open(allowed_index_html, "w") as f:
        f.write("<html>PyRobusta Home</html>")

    # Index page under / -> rejected
    rejected_workdir = normalize_path("/www/rejected")
    rejected_index_html = normalize_path("/www/rejected/index.html")
    mkdir(rejected_workdir)
    with open(rejected_index_html, "w") as f:
        f.write("<html>PyRobusta Home</html>")

    # Case #1: /www/index.html
    response = await send_request(
        (b"GET /allowed/index.html HTTP/1.1\r\n" b"Host: localhost\r\n\r\n")
    )

    response_body = response.split(b"\r\n\r\n")[1]
    test_assert(
        f"test FS access control - index page loaded",
        response_body,
        b"<html>PyRobusta Home</html>",
    )

    # Case #2: /index.html
    response = await send_request(
        (b"GET /rejected/index.html HTTP/1.1\r\n" b"Host: localhost\r\n\r\n")
    )

    test_assert(
        f"test FS access control - index page rejected",
        response.startswith(b"HTTP/1.1 403 Forbidden"),
        True,
    )

    remove(allowed_index_html)
    remove(rejected_index_html)
    rmdir(allowed_workdir)
    rmdir(rejected_workdir)
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
    enable_optional_features()


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


test_main()
