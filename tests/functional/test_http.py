import asyncio
import ssl

from pyrobusta.server import http_server
from pyrobusta.protocol import http_multipart
from pyrobusta.protocol.http import (
    HttpEngine,
    enable_optional_features,
    ServerBusyError,
)
from pyrobusta.utils import config

#################################################
# Test helpers
#################################################


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
        return b"Response %s" % i

    return response_generator


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


@HttpEngine.route("/test/multipart", "GET")
def multipart_callback(http_ctx, _):
    part_count = int(http_ctx.headers["x-part-count"])
    return "multipart/form-data", ("text/plain", multipart_response(part_count))


@HttpEngine.route("/test/busy", "POST")
def busy_callback(*_):
    raise ServerBusyError()


async def test_simple_response(tls_enabled):
    setup_config(multipart=False, tls_enabled=tls_enabled)

    # start server as background task
    server = http_server.HttpServer()
    server_task = asyncio.create_task(server.run_server())
    await asyncio.sleep_ms(100)

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


async def test_multipart_response(tls_enabled):
    setup_config(multipart=True, tls_enabled=tls_enabled)

    # start server as background task
    server = http_server.HttpServer()
    server_task = asyncio.create_task(server.run_server())
    await asyncio.sleep_ms(100)

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


async def test_server_busy():
    setup_config()

    server = http_server.HttpServer()
    server_task = asyncio.create_task(server.run_server())
    await asyncio.sleep_ms(100)

    # Test: 1 part
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


#################################################
# Test methods
#################################################


def setup_config(multipart=False, tls_enabled=False):
    config_idx = config.CONFIG_CACHE.index("http_multipart")
    config.CONFIG_CACHE[config_idx + 1] = str(multipart)
    config_idx = config.CONFIG_CACHE.index("tls")
    config.CONFIG_CACHE[config_idx + 1] = str(tls_enabled)
    enable_optional_features()


def test_registration():
    test_assert(
        "simple endpoint registration",
        simple_callback,
        HttpEngine._get_callback(b"/test/simple", b"GET"),
    )

    test_assert(
        "multipart endpoint registration",
        multipart_callback,
        HttpEngine._get_callback(b"/test/multipart", b"GET"),
    )

    test_assert(
        "busy endpoint registration",
        busy_callback,
        HttpEngine._get_callback(b"/test/busy", b"POST"),
    )


def test_multipart_patches():
    setup_config(multipart=True)
    test_assert(
        "multipart state machine patches",
        http_multipart._start_multipart_parser_st,
        HttpEngine._start_multipart_parser_st,
    )


def test_main():
    test_registration()
    asyncio.run(test_simple_response(tls_enabled=False))
    asyncio.run(test_simple_response(tls_enabled=True))

    test_multipart_patches()
    asyncio.run(test_multipart_response(tls_enabled=False))
    asyncio.run(test_multipart_response(tls_enabled=True))

    asyncio.run(test_server_busy())


test_main()
