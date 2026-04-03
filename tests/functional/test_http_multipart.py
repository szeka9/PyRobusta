import asyncio
import ssl
import gc

from pyrobusta.server import http_server
from pyrobusta.protocol import http_multipart
from pyrobusta.protocol.http import (
    HttpEngine,
    enable_optional_features,
)
from pyrobusta.utils import config

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


def multipart_response(num_responses):
    i = 0

    def response_generator():
        nonlocal i
        i += 1
        if i > num_responses:
            return None
        return "text/plain", b"Response %s" % i

    return response_generator


#################################################
# Test driver
#################################################


@HttpEngine.route("/test/multipart", "GET")
def multipart_callback(http_ctx, _):
    part_count = int(http_ctx.headers["x-part-count"])
    return "multipart/form-data", multipart_response(part_count)


async def start_server():
    """
    Start an HTTP server as a background task
    """
    server = http_server.HttpServer()
    server_task = asyncio.create_task(server.start_socket_server())
    await asyncio.sleep_ms(100)
    return server, server_task


@garbage_collect
async def test_multipart_response(tls_enabled):
    setup_config(tls_enabled=tls_enabled)
    server, server_task = await start_server()

    # Test: 1 part
    plain_response = await send_request(
        b"GET /test/multipart HTTP/1.1\r\n"
        b"Host: localhost\r\nX-Part-Count: 1\r\n\r\n",
        tls_enabled,
    )
    test_assert(
        f"http{"s" if tls_enabled else ""} response contains 1 part",
        b"Response 1" in plain_response,
        True,
    )

    # Test: 10 parts
    plain_response = await send_request(
        b"GET /test/multipart HTTP/1.1\r\n"
        b"Host: localhost\r\nX-Part-Count: 10\r\n\r\n",
        tls_enabled,
    )
    test_assert(
        f"http{"s" if tls_enabled else ""} response contains 10 parts",
        [b"Response %s" % i in plain_response for i in range(1, 11)],
        [True] * 10,
    )

    server_task.cancel()
    await server.terminate()


#################################################
# Test methods
#################################################


def setup_config(tls_enabled=False):
    http_server.HttpServer.LISTEN_PORT_HTTP = 8080
    http_server.HttpServer.LISTEN_PORT_HTTPS = 4443

    config_idx = config.CONFIG_CACHE.index("log_level")
    config.CONFIG_CACHE[config_idx + 1] = str("warning")
    config_idx = config.CONFIG_CACHE.index("http_multipart")
    config.CONFIG_CACHE[config_idx + 1] = "True"
    config_idx = config.CONFIG_CACHE.index("tls")
    config.CONFIG_CACHE[config_idx + 1] = str(tls_enabled)
    enable_optional_features()


def test_registration():
    test_assert(
        "multipart endpoint registration",
        multipart_callback,
        HttpEngine._get_callback(b"/test/multipart", b"GET"),
    )


def test_multipart_patches():
    setup_config()
    test_assert(
        "multipart state machine patches",
        http_multipart._start_multipart_parser_st,
        HttpEngine._start_multipart_parser_st,
    )


def test_main():
    test_registration()
    test_multipart_patches()
    asyncio.run(test_multipart_response(tls_enabled=False))
    asyncio.run(test_multipart_response(tls_enabled=True))


test_main()
