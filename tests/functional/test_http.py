import asyncio

from pyrobusta.server import http_server
from pyrobusta.protocol.http import HttpEngine


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


def test_endpoint(headers, body):
    if headers["accept"] == "text/plain":
        return "text/plain", "Test response\n"
    elif headers["accept"] == "application/json":
        return "application/json", '{"response": "Test response"}'
    raise ValueError("Unhandled content-type")


def test_registration():
    run_test(
        "endpoint registration",
        test_endpoint,
        HttpEngine.ENDPOINTS[b"/test"][b"GET"],
    )


async def test_response():
    # start server as background task
    server_task = asyncio.create_task(http_server.HttpServer().run_server())

    # give server time to bind socket
    await asyncio.sleep(1)

    # Test: text/plain
    plain_response = await send_request(
        b"GET /test HTTP/1.1\r\n" b"Host: localhost\r\nAccept:text/plain\r\n" b"\r\n"
    )
    run_test(
        "http response contains text/plain header",
        b"text/plain" in plain_response,
        True,
    )
    run_test(
        "http response contains text/plain body",
        b"Test response" in plain_response,
        True,
    )

    # Test: application/json
    json_response = await send_request(
        b"GET /test HTTP/1.1\r\n"
        b"Host: localhost\r\nAccept:application/json\r\n"
        b"\r\n"
    )
    run_test(
        "http response contains application/json header",
        b"application/json" in json_response,
        True,
    )
    run_test(
        "http response contains application/json body",
        b'{"response": "Test response"}' in json_response,
        True,
    )

    server_task.cancel()


def setup():
    HttpEngine.register("/test", test_endpoint)


def test():
    test_registration()
    asyncio.run(test_response())


setup()
test()
