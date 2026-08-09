import asyncio
import ssl
import gc

from os import mkdir, listdir, remove, rmdir

from pyrobusta.server import http_server
from pyrobusta.protocol.http import enable_optional_features
from pyrobusta.utils.iam import IAMDatabase
from pyrobusta.utils.config import (
    CONF_TLS,
    CONF_LOG_LEVEL,
    CONF_HTTP_MULTIPART,
    CONF_HTTP_FILES_API,
    CONF_HTTP_SERVED_PATHS,
    CONF_HTTP_AUTH,
    CONF_HTTP_BROWSER_SECURITY,
    CONF_HTTP_INSECURE_AUTH,
    CONF_HTTP_SESSIONS,
    CONF_HTTP_SESSION_TTL_SEC,
    CONF_PASSWD_FILE,
    CONF_ROLES_FILE,
    _CONFIG_CACHE,
    parse_config,
    get_config,
)


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


async def start_server():
    """
    Start an HTTP server as a background task.
    """
    server = http_server.HttpServer()
    await server.start_socket_server()
    await asyncio.sleep_ms(100)
    return server


async def send_request(request):
    is_tls = get_config(CONF_TLS)
    port = (
        http_server.HttpServer.LISTEN_PORT_HTTPS
        if is_tls
        else http_server.HttpServer.LISTEN_PORT_HTTP
    )

    ctx = None
    if is_tls:
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


def setup_config(
    tls_enabled=False,
    files_api_enabled=False,
    http_multipart_enabled=False,
    served_paths="",
    http_auth="",
    http_browser_security=True,
    http_insecure_auth=False,
    http_sessions=False,
    http_session_ttl_sec=900,
):
    http_server.HttpServer.LISTEN_PORT_HTTP = 8080
    http_server.HttpServer.LISTEN_PORT_HTTPS = 4443

    _CONFIG_CACHE[CONF_LOG_LEVEL] = "warning"
    _CONFIG_CACHE[CONF_TLS] = tls_enabled
    _CONFIG_CACHE[CONF_HTTP_SERVED_PATHS] = parse_config(
        CONF_HTTP_SERVED_PATHS, served_paths
    )
    _CONFIG_CACHE[CONF_HTTP_MULTIPART] = http_multipart_enabled
    _CONFIG_CACHE[CONF_HTTP_FILES_API] = files_api_enabled
    _CONFIG_CACHE[CONF_HTTP_AUTH] = http_auth
    _CONFIG_CACHE[CONF_HTTP_BROWSER_SECURITY] = http_browser_security
    _CONFIG_CACHE[CONF_HTTP_INSECURE_AUTH] = http_insecure_auth
    _CONFIG_CACHE[CONF_HTTP_SESSIONS] = http_sessions
    _CONFIG_CACHE[CONF_HTTP_SESSION_TTL_SEC] = http_session_ttl_sec

    iam_db = None
    if get_config(CONF_HTTP_AUTH):
        iam_db = IAMDatabase(get_config(CONF_PASSWD_FILE), get_config(CONF_ROLES_FILE))
        if not iam_db.load():
            raise RuntimeError("Unable to initialize IAM")

    enable_optional_features(iam_db)
