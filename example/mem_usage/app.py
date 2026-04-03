import asyncio
from gc import mem_free, mem_alloc, collect

import pyrobusta.server.http_server as http_server
from pyrobusta.protocol.http import HttpEngine
from pyrobusta.utils import logging


@HttpEngine.route("/mem-usage", "GET")
def mem_usage(http_ctx, _):
    collect()
    free = mem_free()
    used = mem_alloc()
    usage_percentage = 100 * used / (free + used)

    if http_ctx.query:
        value_format = http_ctx.get_url_encoded_query_param(
            http_ctx.query, "format", "bytes"
        )
        if value_format not in ("%", "bytes"):
            raise ValueError("invalid format")

        selector = http_ctx.get_url_encoded_query_param(http_ctx.query, "key", "")
        if selector == "free":
            if value_format == "%":
                free = round(100 * free / (used + free),2)
            return "text/plain", f"Free   [{value_format}]: {free}\n"
        if selector == "used":
            if value_format == "%":
                used = round(100 * used / (used + free),2)
            return "text/plain", f"Used   [{value_format}]: {used}\n"
        if selector == "total":
            return "text/plain", f"Total  [bytes]: {used + free}\n"

        if selector:
            raise ValueError("invalid key")

    return "text/plain", (
        f"Currently used: {usage_percentage:.2f}%\n"
        f"Free   [bytes]: {free}\n"
        f"Used   [bytes]: {used}\n"
        f"Total  [bytes]: {used + free}\n"
    )


http_server.main()

try:
    asyncio.get_event_loop().run_forever()
except Exception as e:
    logging.warning(f"[asyncio] loop stopped: {e}")
    asyncio.get_event_loop().close()
