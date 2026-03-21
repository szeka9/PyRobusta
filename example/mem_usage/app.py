import asyncio
from gc import mem_free, mem_alloc, collect

import pyrobusta.server.http_server as http_server
from pyrobusta.protocol.http import HttpEngine
from pyrobusta.utils import logging


@HttpEngine.route("/mem-usage", "GET")
def mem_usage(*_):
    collect()
    free = mem_free()
    used = mem_alloc()
    usage_percentage = 100 * used / (free + used)
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
