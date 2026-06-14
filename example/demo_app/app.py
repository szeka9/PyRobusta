import asyncio

from pyrobusta.server import http_server
from pyrobusta.protocol.http import HttpEngine
from pyrobusta.utils.config import PYROBUSTA_VERSION

APP_VERSION = "v0.0.1"


@HttpEngine.route("/version", "GET")
def version(http_ctx, _):
    include_server_version = False

    if http_ctx.query:
        is_detailed = http_ctx.get_query_param(
            "detailed", default="false"
        ).lower()

        if is_detailed not in ("true", "false"):
            http_ctx.terminate(400, True)
            return "text/plain", "Invalid query"

        include_server_version = is_detailed.lower() == "true"

    if http_ctx.headers.get("accept") == "application/json":
        version_dict = {"app_version": APP_VERSION}
        if include_server_version:
            version_dict["server_version"] = PYROBUSTA_VERSION
        return "application/json", version_dict

    version_text = f"app_version: {APP_VERSION}\n"
    if include_server_version:
        version_text += f"server_version: {PYROBUSTA_VERSION}\n"
    return "text/plain", version_text


@HttpEngine.route("/{app_or_server}/version", "GET")
def version(http_ctx, _):
    include_server_version = False
    resource = http_ctx.url.split(b"/")[1]

    if resource not in (b"app", b"server"):
        http_ctx.terminate(404, True)
        return "text/plain", "Not found"

    version_string = APP_VERSION if resource == b"app" else PYROBUSTA_VERSION

    if http_ctx.headers.get("accept") == "application/json":
        return "application/json", {"version": version_string}

    return "text/plain", f"{version_string}\n"


async def main():
    server = http_server.HttpServer()
    asyncio.create_task(server.start_socket_server())
    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())