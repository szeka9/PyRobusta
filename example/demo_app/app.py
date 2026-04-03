import asyncio
from gc import mem_free, mem_alloc

from pyrobusta.server import http_server
from pyrobusta.protocol.http import HttpEngine
from pyrobusta.utils import logging


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


def main():
    http_server.main()
    try:
        asyncio.get_event_loop().run_forever()
    except Exception as e:
        logging.warning(f"loop stopped: {e}")
        asyncio.get_event_loop().close()
