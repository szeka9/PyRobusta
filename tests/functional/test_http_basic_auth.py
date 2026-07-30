import asyncio

from pyrobusta.protocol import http_basic_auth
from pyrobusta.protocol.http import HttpEngine
from pyrobusta.utils.config import (
    CONF_HTTP_SESSION_TTL_SEC,
    get_config,
)
from env_utils import (
    garbage_collect,
    get_config,
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
    setup_config(http_auth="basic", tls_enabled=True)
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
    setup_config(http_auth="basic", tls_enabled=True)
    server = await start_server()

    # Test: authenticated & unauthorized
    plain_response = await send_request(
        b"GET /test/auth HTTP/1.1\r\n"
        b"Host: localhost\r\n"
        b"Content-Length: 0\r\n"
        b"Authorization: Basic YWxpY2U6YWxpY2Uncy1zZWNyZXQtcGFzc3dvcmQ=\r\n"
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
    setup_config(http_auth="basic", tls_enabled=True)
    server = await start_server()

    # Test: authenticated & authorized
    plain_response = await send_request(
        b"GET /test/auth HTTP/1.1\r\n"
        b"Host: localhost\r\n"
        b"Content-Length: 0\r\n"
        b"Authorization: Basic Ym9iOmJvYidzLXNlY3JldC1wYXNzd29yZA==\r\n"
        b"Connection: close\r\n\r\n"
    )

    test_assert(
        f"request accepted with 200 OK",
        b"200 OK" in plain_response,
        True,
    )

    await server.terminate()


@garbage_collect
async def test_server_prevents_insecure_auth():
    exception_raised = False
    try:
        setup_config(http_auth="basic", tls_enabled=False, http_insecure_auth=False)
    except ValueError:
        exception_raised = True

    test_assert(
        f"server prevents authentication without TLS",
        exception_raised,
        True,
    )


@garbage_collect
async def test_server_basic_auth_with_sessions():
    setup_config(
        http_auth="basic",
        http_auth_mode="api",  # Disabling CSRF for session tests
        http_sessions="true",
        http_session_ttl_sec=5,
        tls_enabled=True,
    )
    server = await start_server()

    # Test: authenticated & authorized
    plain_response = await send_request(
        b"GET /test/auth HTTP/1.1\r\n"
        b"Host: localhost\r\n"
        b"Content-Length: 0\r\n"
        b"Authorization: Basic Ym9iOmJvYidzLXNlY3JldC1wYXNzd29yZA==\r\n"
        b"Connection: close\r\n\r\n"
    )

    session_cookie_start = plain_response.find(b"session=")
    session_cookie_end = plain_response.find(b";", session_cookie_start)
    session_cookie = plain_response[session_cookie_start:session_cookie_end]

    test_assert(
        f"response contains session cookie with 200 OK",
        b"200 OK" in plain_response,
        True,
    )

    plain_response = await send_request(
        b"GET /test/auth HTTP/1.1\r\n"
        b"Host: localhost\r\n"
        b"Content-Length: 0\r\n"
        b"Cookie: " + session_cookie + b"\r\n"
        b"Connection: close\r\n\r\n"
    )

    test_assert(
        f"request accepted with 200 OK using session cookie",
        b"200 OK" in plain_response,
        True,
    )

    sleep_time = get_config(CONF_HTTP_SESSION_TTL_SEC) + 1
    print(f"Sleeping for {sleep_time} seconds to let the session expire...")
    await asyncio.sleep(sleep_time)

    plain_response = await send_request(
        b"GET /test/auth HTTP/1.1\r\n"
        b"Host: localhost\r\n"
        b"Content-Length: 0\r\n"
        b"Cookie: " + session_cookie + b"\r\n"
        b"Connection: close\r\n\r\n"
    )

    test_assert(
        f"request rejected with 401 Unauthorized after session expiration",
        b"401 Unauthorized" in plain_response,
        True,
    )

    await server.terminate()


def setup_auth():
    with open("pyrobusta.passwd", "w") as users:
        users.write(
            "alice:role-1:mKmmf5wBEtlkty7LEcphieciOd3Pl0yY7r3WmDiZnzg=:XTQgg3Has79lDTNYVW+aPw==:5000:PBKDF2-HMAC-SHA256:v1.2.3\n"
        )
        users.write(
            "bob:role-2:sOqLqi48jCQUiR+VpcCcfMgKcKCspbE902y0yFe0DV4=:5PzMbQQJtQRP8aZ9C7t8qQ==:5000:PBKDF2-HMAC-SHA256:v1.2.3\n"
        )

    with open("pyrobusta.roles", "w") as users:
        users.write("/test/auth\n*:role-2\n")


def test_registration():
    test_assert(
        "auth route registration",
        auth_handler,
        HttpEngine._get_handler(b"/test/auth", b"GET"),
    )


def test_auth_patches():
    setup_auth()
    setup_config(http_auth="basic", tls_enabled=True)
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
    await test_server_prevents_insecure_auth()
    await test_server_basic_auth_with_sessions()


asyncio.run(test_main())
