import os
import time
import sys

from server import Server, LocalServer, DeviceServer
from utils import test_assert, send_request

BOOT_SCRIPT = """
import asyncio
import machine

from pyrobusta.protocol.http import HttpEngine
from pyrobusta import application


@HttpEngine.route("/test/auth", "GET")
def auth_handler(http_ctx, _):
    return "text/plain", "OK"

async def main():
    await application.run()
    while True:
        await asyncio.sleep(1)

asyncio.run(main())
"""


def test_missing_auth_header(srv: Server):
    srv.setup_config(http_auth="basic", tls=True)
    srv.start(BOOT_SCRIPT)

    try:
        # Test: unauthenticated & unauthorized
        plain_response = send_request(
            srv,
            b"GET /test/auth HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Length: 0\r\n"
            b"Connection: close\r\n\r\n",
        )

        test_assert(
            f"request rejected with 401 Unauthorized",
            b"401 Unauthorized" in plain_response,
            True,
        )
    finally:
        srv.terminate()


def test_missing_role(srv: Server):
    srv.setup_config(http_auth="basic", tls=True)
    srv.start(BOOT_SCRIPT)

    try:
        # Test: authenticated & unauthorized
        plain_response = send_request(
            srv,
            b"GET /test/auth HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Length: 0\r\n"
            b"Authorization: Basic YWxpY2U6YWxpY2Uncy1zZWNyZXQtcGFzc3dvcmQ=\r\n"
            b"Connection: close\r\n\r\n",
        )

        test_assert(
            f"request rejected with 403 Forbidden",
            b"403 Forbidden" in plain_response,
            True,
        )
    finally:
        srv.terminate()


def test_user_authorized(srv: Server):
    srv.setup_config(http_auth="basic", tls=True)
    srv.start(BOOT_SCRIPT)

    try:
        # Test: authenticated & authorized
        plain_response = send_request(
            srv,
            b"GET /test/auth HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Length: 0\r\n"
            b"Authorization: Basic Ym9iOmJvYidzLXNlY3JldC1wYXNzd29yZA==\r\n"
            b"Connection: close\r\n\r\n",
        )

        test_assert(
            f"request accepted with 200 OK",
            b"200 OK" in plain_response,
            True,
        )
    finally:
        srv.terminate()


def test_server_prevents_insecure_auth(srv: Server):
    srv.setup_config(http_auth="basic", tls=False, http_insecure_auth=False)
    srv.start(BOOT_SCRIPT, healthcheck=False)

    exception_raised = False
    try:
        send_request(
            srv,
            b"GET /test/auth HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Length: 0\r\n"
            b"Authorization: Basic Ym9iOmJvYidzLXNlY3JldC1wYXNzd29yZA==\r\n"
            b"Connection: close\r\n\r\n",
        )
    except ConnectionRefusedError:
        exception_raised = True
    finally:
        srv.terminate()

    test_assert(
        f"server prevents authentication without TLS",
        exception_raised,
        True,
    )


def test_server_basic_auth_with_sessions(srv: Server):
    srv.setup_config(
        http_auth="basic",
        http_browser_security=False,  # Disabling CSRF for session tests
        http_sessions=True,
        http_session_ttl_sec=5,
        tls=True,
    )
    srv.start(BOOT_SCRIPT)

    try:
        # Test: authenticated & authorized
        plain_response = send_request(
            srv,
            b"GET /test/auth HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Length: 0\r\n"
            b"Authorization: Basic Ym9iOmJvYidzLXNlY3JldC1wYXNzd29yZA==\r\n"
            b"Connection: close\r\n\r\n",
        )

        session_cookie_start = plain_response.find(b"session=")
        session_cookie_end = plain_response.find(b";", session_cookie_start)
        session_cookie = plain_response[session_cookie_start:session_cookie_end]

        test_assert(
            f"response contains session cookie with 200 OK",
            b"200 OK" in plain_response,
            True,
        )

        plain_response = send_request(
            srv,
            b"GET /test/auth HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Length: 0\r\n"
            b"Cookie: " + session_cookie + b"\r\n"
            b"Connection: close\r\n\r\n",
        )

        test_assert(
            f"request accepted with 200 OK using session cookie",
            b"200 OK" in plain_response,
            True,
        )

        sleep_time = srv.config.get("http_session_ttl_sec") + 1
        print(f"Sleeping for {sleep_time} seconds to let the session expire...")
        time.sleep(sleep_time)

        plain_response = send_request(
            srv,
            b"GET /test/auth HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Length: 0\r\n"
            b"Cookie: " + session_cookie + b"\r\n"
            b"Connection: close\r\n\r\n",
        )

        test_assert(
            f"request rejected with 401 Unauthorized after session expiration",
            b"401 Unauthorized" in plain_response,
            True,
        )
    finally:
        srv.terminate()


def setup_auth(srv: Server):
    srv.write_file(
        "/pyrobusta.passwd",
        (
            "alice:role-1:mKmmf5wBEtlkty7LEcphieciOd3Pl0yY7r3WmDiZnzg=:XTQgg3Has79lDTNYVW+aPw==:5000:PBKDF2-HMAC-SHA256:v1.2.3\n"
            "bob:role-2:sOqLqi48jCQUiR+VpcCcfMgKcKCspbE902y0yFe0DV4=:5PzMbQQJtQRP8aZ9C7t8qQ==:5000:PBKDF2-HMAC-SHA256:v1.2.3\n"
        ),
    )

    srv.write_file(
        "/pyrobusta.roles",
        ("/test/auth\n" "*:role-2\n"),
    )


def test_main(srv: Server):
    setup_auth(srv)

    test_missing_auth_header(srv)
    test_missing_role(srv)
    test_user_authorized(srv)
    test_server_prevents_insecure_auth(srv)
    test_server_basic_auth_with_sessions(srv)


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
