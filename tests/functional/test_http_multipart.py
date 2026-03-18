import asyncio

from pyrobusta.server import http_server
from pyrobusta.protocol import http, http_multipart
from pyrobusta.utils import config


def run_test(name, actual, expected):
    print(f"Test {name}: ", end="")
    if actual == expected:
        print("OK")
    else:
        print("Fail")
        raise AssertionError(f"{actual} != {expected}")


async def send_request(request):
    reader, writer = await asyncio.open_connection("127.0.0.1", 8000)
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


def multipart_callback(headers, body):
    part_count = int(headers["x-part-count"])
    return "multipart/form-data", ("text/plain", multipart_response(part_count))


def test_patches():
    run_test(
        "multipart state machine patches",
        http_multipart._start_multipart_parser_st,
        http.HttpEngine._start_multipart_parser_st,
    )


async def test_response():
    # start server as background task
    server_task = asyncio.create_task(http_server.HttpServer().run_server())

    # give server time to bind socket
    await asyncio.sleep(1)

    # Test: 1 part
    plain_response = await send_request(
        b"GET /test HTTP/1.1\r\n" b"Host: localhost\r\nX-Part-Count: 1\r\n\r\n"
    )
    run_test(
        "http response contains 1 part",
        b"Response 1" in plain_response,
        True,
    )

    # Test: 10 parts
    plain_response = await send_request(
        b"GET /test HTTP/1.1\r\n" b"Host: localhost\r\nX-Part-Count: 10\r\n\r\n"
    )
    run_test(
        f"http response contains 10 parts",
        [b"Response %s" % i in plain_response for i in range(1, 11)],
        [True] * 10,
    )

    server_task.cancel()


def setup():
    config_idx = config.CONFIG_CACHE.index("http_multipart")
    config.CONFIG_CACHE[config_idx + 1] = "True"
    http.enable_optional_features()
    http.HttpEngine.register("/test", multipart_callback)


def test():
    test_patches()
    asyncio.run(test_response())


setup()
test()
