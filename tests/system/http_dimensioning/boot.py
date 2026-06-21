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


@HttpEngine.route("/mem/current", "GET")
def current_usage(*_):
    collect()
    return "text/plain", str(mem_alloc())


@HttpEngine.route("/mem/time-series", "GET")
def time_series(*_):
    return "application/json", MEM_TIME_SERIES


@HttpEngine.route("/test/stream", "POST")
def chunked_handler(http_ctx, chunk_or_part):
    if (
        http_ctx.headers.get("content-type", "").startswith("multipart/form-data")
        and http_ctx.mp_is_last
    ):
        return "text/plain", "OK"
    elif not chunk_or_part:  # Received terminating chunk/part
        return "text/plain", "OK"
    pass  # process chunk/part data as needed


async def mem_usage():
    i = 0
    collect()
    while True:
        i = (i + 1) % TS_DURATION
        collect()
        MEM_TIME_SERIES[i] = mem_alloc()
        await asyncio.sleep(1)


async def main():
    server = http_server.HttpServer()
    connected = wifi.initialize()
    if connected and not machine.reset_cause() == machine.SOFT_RESET:
        if get_config(CONF_HTTP_MULTIPART):

            def multipart_response(num_responses, part_size):
                i = 0

                def response_generator():
                    nonlocal i
                    i += 1
                    if i > num_responses:
                        return None
                    return "text/plain", b"X" * part_size

                return response_generator

            def multipart_handler(http_ctx, _):
                part_count = int(http_ctx.headers.get("x-part-count", 1))
                part_size = int(http_ctx.headers.get("x-part-size", 1024))
                return "multipart/form-data", multipart_response(part_count, part_size)

            HttpEngine.register("/test/multipart", multipart_handler, "GET")

        asyncio.create_task(server.start_socket_server())
        asyncio.create_task(mem_usage())
        while True:
            await asyncio.sleep(1)


asyncio.run(main())
