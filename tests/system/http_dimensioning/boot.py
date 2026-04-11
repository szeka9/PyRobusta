# This file is executed on every boot (including wake-boot from deepsleep)
import machine
import asyncio
from gc import mem_alloc, collect

import pyrobusta.server.http_server as http_server
from pyrobusta.protocol.http import HttpEngine
from pyrobusta.connectivity import wifi

TS_DURATION = 100
MEM_TIME_SERIES = [0] * TS_DURATION


@HttpEngine.route("/mem/current", "GET")
def current_usage(*_):
    collect()
    return "text/plain", str(mem_alloc())


@HttpEngine.route("/mem/time-series", "GET")
def time_series(*_):
    return "application/json", MEM_TIME_SERIES


async def mem_usage():
    i = 0
    collect()
    while True:
        i = (i + 1) % TS_DURATION
        MEM_TIME_SERIES[i] = mem_alloc()
        await asyncio.sleep(1)


async def main():
    server = http_server.HttpServer()
    connected = wifi.initialize()
    if connected and not machine.reset_cause() == machine.SOFT_RESET:
        asyncio.create_task(server.start_socket_server())
        asyncio.create_task(mem_usage())
        while True:
            await asyncio.sleep(1)


asyncio.run(main())
