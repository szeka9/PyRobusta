# This file is executed on every boot (including wake-boot from deepsleep)
import machine
import asyncio
from gc import mem_alloc, collect

import pyrobusta.server.http_server as http_server
from pyrobusta.protocol.http import HttpEngine
from pyrobusta.connectivity import wifi

from pyrobusta.utils.config import get_config, CONF_HTTP_MULTIPART

TS_DURATION = 100
MEM_TIME_SERIES = [0] * TS_DURATION


@HttpEngine.route("/heap/time-series", "GET")
def time_series(*_):
    return "application/json", MEM_TIME_SERIES


async def mem_usage():
    i = 0
    collect()
    while True:
        collect()
        MEM_TIME_SERIES[i] = mem_alloc()
        await asyncio.sleep(1)
        i = (i + 1) % TS_DURATION


async def main():
    server = http_server.HttpServer()
    connected = wifi.initialize()
    if connected and not machine.reset_cause() == machine.SOFT_RESET:
        import app_base

        app_base.load()

        if get_config(CONF_HTTP_MULTIPART):
            import app_multipart

            app_multipart.load()

        asyncio.create_task(server.start_socket_server())
        asyncio.create_task(mem_usage())

        while True:
            await asyncio.sleep(1)


asyncio.run(main())
