import asyncio
from gc import mem_free, mem_alloc, collect

import pyrobusta.server.http_server as http_server
from pyrobusta.protocol.http import HttpEngine


@HttpEngine.route("/mem-usage", "GET")
def mem_usage(http_ctx, _):
    collect()
    free = mem_free()
    used = mem_alloc()
    usage_percentage = 100 * used / (free + used)

    if http_ctx.query:
        value_format = http_ctx.get_query_param("format", "bytes")
        if value_format not in ("%", "bytes"):
            http_ctx.terminate(400)
            return "text/plain", "Invalid query"

        selector = http_ctx.get_query_param("key", "")
        if selector == "free":
            if value_format == "%":
                free = round(100 * free / (used + free), 2)
            return "text/plain", f"Free   [{value_format}]: {free}\n"
        if selector == "used":
            if value_format == "%":
                used = round(100 * used / (used + free), 2)
            return "text/plain", f"Used   [{value_format}]: {used}\n"
        if selector == "total":
            return "text/plain", f"Total  [bytes]: {used + free}\n"

        if selector:
            http_ctx.terminate(400)
            return "text/plain", "Invalid query"


    return "text/plain", (
        f"Currently used: {usage_percentage:.2f}%\n"
        f"Free   [bytes]: {free}\n"
        f"Used   [bytes]: {used}\n"
        f"Total  [bytes]: {used + free}\n"
    )


async def main():
    server = http_server.HttpServer()
    await server.start_socket_server()
    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
