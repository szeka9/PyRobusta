"""
Top-level application for server configuration and initialization.
"""

# pylint: disable=C0413
import gc

from pyrobusta.server.http_server import HttpServer
from pyrobusta.protocol import http

gc.collect()

from pyrobusta.utils.config import Config
from pyrobusta import WORKING_DIR
from pyrobusta.utils.logging import set_log_level, error, info

gc.collect()


def _patch_module(name, config, auth_provider):
    module = __import__(
        "pyrobusta.protocol." + name, globals(), locals(), ("apply_patches",)
    )
    module.apply_patches(http.HttpEngine, config, auth_provider)
    gc.collect()


def _load_iam(config):
    iam_db = None
    if config.http_auth:
        iam = __import__("pyrobusta.utils.iam", globals(), locals(), ("IAMDatabase",))
        iam_db = iam.IAMDatabase(
            config.passwd_file,
            config.roles_file,
        )
        if not iam_db.load():
            raise RuntimeError("Failed to initialize IAM")
        gc.collect()
    return iam_db


def init_wifi(ssid, password):
    """
    Initialize WLAN station interface.
    """
    from time import sleep
    from network import WLAN, STA_IF

    if not ssid or not password:
        error("%s: missing SSID/password", __name__)
        return False

    sta_if = WLAN(STA_IF)
    sta_if.active(True)

    if sta_if.isconnected():
        addr = sta_if.ifconfig()[0]
        info("%s: already connected ip=[%s]", __name__, addr)
        return True

    sta_if.connect(ssid, password)

    timeout = 30
    while timeout > 0:
        if sta_if.isconnected():
            addr = sta_if.ifconfig()[0]
            info("%s: connected, ip=[%s]", __name__, addr)
            return True
        sleep(1)
        timeout -= 1

    error("%s: connection failed", __name__)
    return False


async def run():
    """
    Start the server by creating an async task.
    Additionally, read configuration and set up optional features.
    """

    config = Config(WORKING_DIR + "/pyrobusta.env")
    set_log_level(config.log_level)

    ssl_ctx = None
    if config.tls:
        import ssl

        ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_ctx.load_cert_chain(
            config.tls_cert_file,
            config.tls_key_file,
        )

    iam_db = _load_iam(config)

    http.apply_patches(config)
    gc.collect()
    if config.http_multipart:
        _patch_module("http_multipart", config, iam_db)
    if config.http_auth == "basic":
        _patch_module("http_basic_auth", config, iam_db)
    if config.http_files_api:
        _patch_module("http_file_server", config, iam_db)
    if config.http_browser_security:
        _patch_module("http_security", config, iam_db)

    if config.wifi_ssid:
        init_wifi(config.wifi_ssid, config.wifi_password)

    server = HttpServer()
    await server.start_socket_server(
        "0.0.0.0",
        config.https_port if config.tls else config.http_port,
        config.socket_max_con,
        config.http_mem_cap,
        ssl_ctx,
    )

    del config
    gc.collect()
