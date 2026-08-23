import asyncio

from pyrobusta import application
from pyrobusta.protocol.http import HttpEngine
from pyrobusta.utils import logging, assets, lexpath
from pyrobusta import PYROBUSTA_VERSION


def append_package_files(dir, package_files, host_name, protocol):
    """
    Construct package file list recursively.
    """
    dir = lexpath.normalize_path(dir)

    for asset in assets.iterate_fs(dir):
        package_files["urls"].append(
            [
                asset,
                f"{protocol}://{host_name}/files" + asset,
            ]
        )


@HttpEngine.route("/pyrobusta/package.json", "GET")
def self_serve_mip_package(http_ctx, _):
    package_files = {"version": PYROBUSTA_VERSION, "deps": [], "urls": []}
    server_addr = http_ctx.headers["host"]
    protocol = "https" if http_ctx.tls else "http"

    logging.debug("mip_repo addr=[%s]", server_addr)
    append_package_files("/lib/pyrobusta", package_files, server_addr, protocol)
    return "application/json", package_files


async def main():
    await application.run()

    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
