import asyncio
import os

import pyrobusta.server.http_server as http_server
from pyrobusta.protocol.http import HttpEngine
from pyrobusta.utils import logging, config


def append_package_files(dir, package_files, host_name, protocol):
    """
    Construct package file list recursively.
    """
    for name in os.listdir(dir):
        current_path = f"{dir}/{name}"
        st = os.stat(current_path)
        mode = st[0]
        if mode & 0x4000:  # directory bit set
            append_package_files(current_path, package_files, host_name, protocol)
            continue

        target_path = current_path[4:] if current_path.startswith("lib/") else current_path
        package_files["urls"].append(
            [
                target_path,
                f"{protocol}://{host_name}/{current_path}",
            ]
        )


@HttpEngine.route("/pyrobusta/package.json", "GET")
def self_serve_mip_package(http_ctx, _):
    package_files = {"version": config.PYROBUSTA_VERSION, "deps": [], "urls": []}
    tls_enabled = config.get_config("tls").lower() == "true"
    server_addr = http_ctx.headers["host"]
    if ":" not in server_addr:
        port = (
            http_server.HttpServer.LISTEN_PORT_HTTPS
            if tls_enabled
            else http_server.HttpServer.LISTEN_PORT_HTTP
        )
        if not server_addr in (80, 443):
            server_addr += f":{port}"

    protocol = "https" if tls_enabled else "http"

    logging.debug(f"[mip_repo] server_addr: {server_addr}")
    root = "pyrobusta" if "pyrobusta" in os.listdir() else "lib/pyrobusta"
    append_package_files(root, package_files, server_addr, protocol)
    return "application/json", package_files


http_server.main()

try:
    asyncio.get_event_loop().run_forever()
except Exception as e:
    logging.warning(f"[asyncio] loop stopped: {e}")
    asyncio.get_event_loop().close()
