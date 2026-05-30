import asyncio

import pyrobusta.server.http_server as http_server
from pyrobusta.protocol.http import HttpEngine
from pyrobusta.utils import logging, config, assets, helpers


def append_package_files(dir, package_files, host_name, protocol):
    """
    Construct package file list recursively.
    """
    dir = helpers.normalize_path(dir)

    for asset in assets.iterate_fs(dir):
        package_files["urls"].append(
            [
                asset,
                f"{protocol}://{host_name}/files" + asset,
            ]
        )


@HttpEngine.route("/pyrobusta/package.json", "GET")
def self_serve_mip_package(http_ctx, _):
    package_files = {"version": config.PYROBUSTA_VERSION, "deps": [], "urls": []}
    tls_enabled = config.get_config(config.CONF_TLS)
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
    append_package_files("/lib/pyrobusta", package_files, server_addr, protocol)
    return "application/json", package_files


async def main():
    server = http_server.HttpServer()
    asyncio.create_task(server.start_socket_server())
    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())