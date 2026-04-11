import asyncio
from gc import mem_free, mem_alloc

from pyrobusta.server import http_server
from pyrobusta.protocol.http import HttpEngine


@HttpEngine.route("/app", "GET")
def app(http_ctx, payload):
    free = mem_free()
    value_format = "bytes"

    if http_ctx.query:
        value_format = http_ctx.get_url_encoded_query_param(
            http_ctx.query, "format", default="bytes"
        )
        if value_format not in ("%", "bytes"):
            raise ValueError("invalid format")

        if value_format == "%":
            free = round(100 * free / (free + mem_alloc()), 2)

    return "text/plain", (f"Free memory [{value_format}]: {free}\n")


async def main():
    server = http_server.HttpServer()
    asyncio.create_task(server.start_socket_server())
    while True:
        await asyncio.sleep(1)
