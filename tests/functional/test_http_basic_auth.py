import asyncio

from pyrobusta.protocol import http_basic_auth
from pyrobusta.protocol.http import HttpEngine
from env_utils import (
    garbage_collect,
    test_assert,
    send_request,
    setup_config,
    start_server,
)


@HttpEngine.route("/test/auth", "GET")
def auth_handler(http_ctx, _):
    return "text/plain", "OK"


@garbage_collect
async def test_missing_auth_header():
    setup_config(http_auth="basic")
    server = await start_server()

    # Test: unauthenticated & unauthorized
    plain_response = await send_request(
        b"GET /test/auth HTTP/1.1\r\n"
        b"Host: localhost\r\n"
        b"Content-Length: 0\r\n"
        b"Connection: close\r\n\r\n"
    )

    test_assert(
        f"request rejected with 401 Unauthorized",
        b"401 Unauthorized" in plain_response,
        True,
    )

    await server.terminate()


@garbage_collect
async def test_missing_role():
    setup_config(http_auth="basic")
    server = await start_server()

    # Test: authenticated & unauthorized
    plain_response = await send_request(
        b"GET /test/auth HTTP/1.1\r\n"
        b"Host: localhost\r\n"
        b"Content-Length: 0\r\n"
        b"Authorization: Basic dXNlcjE6cGFzc3dvcmQx\r\n"
        b"Connection: close\r\n\r\n"
    )

    test_assert(
        f"request rejected with 403 Forbidden",
        b"403 Forbidden" in plain_response,
        True,
    )

    await server.terminate()


@garbage_collect
async def test_user_authorized():
    setup_config(http_auth="basic")
    server = await start_server()

    # Test: authenticated & authorized
    plain_response = await send_request(
        b"GET /test/auth HTTP/1.1\r\n"
        b"Host: localhost\r\n"
        b"Content-Length: 0\r\n"
        b"Authorization: Basic dXNlcjI6cGFzc3dvcmQy\r\n"
        b"Connection: close\r\n\r\n"
    )

    test_assert(
        f"request accepted with 200 OK",
        b"200 OK" in plain_response,
        True,
    )

    await server.terminate()


def setup_auth():
    with open("pyrobusta.passwd", "w") as users:
        users.write(
            "user1:0b14d501a594442a01c6859541bcb3e8164d183d32937b851835442f69d5c94e:role1\n"
        )
        users.write(
            "user2:6cf615d5bcaac778352a8f1f3360d23f02f34ec182e259897fd6ce485d7870d4:role2\n"
        )

    with open("pyrobusta.roles", "w") as users:
        users.write("/test/auth\n*:role2\n")


def test_registration():
    test_assert(
        "auth route registration",
        auth_handler,
        HttpEngine._get_handler(b"/test/auth", b"GET"),
    )


def test_auth_patches():
    setup_auth()
    setup_config(http_auth="basic")
    test_assert(
        "auth state machine patches",
        http_basic_auth._handle_auth_st,
        HttpEngine._handle_auth_st,
    )


async def test_main():
    test_registration()
    test_auth_patches()

    await test_missing_auth_header()
    await test_missing_role()
    await test_user_authorized()


asyncio.run(test_main())
