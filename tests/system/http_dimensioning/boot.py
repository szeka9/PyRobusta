# pylint: disable=E0401,C0415,E1101,E0611
# This file is executed on every boot (including wake-boot from deepsleep)
import asyncio
import os
import time
from gc import mem_alloc, collect
import machine

from pyrobusta.server import http_server
from pyrobusta.connectivity import wifi

from pyrobusta.utils.config import get_config, CONF_HTTP_MULTIPART

LOG_FILE = "heap_usage.csv"

SAMPLE_PERIOD = 5  # seconds
FLUSH_PERIOD = 12  # Flush every minute


async def mem_usage():
    flush_counter = 0
    try:
        os.remove(LOG_FILE)
    except OSError:
        pass
    collect()
    with open(LOG_FILE, "a", encoding="utf-8") as log:
        start_ts = time.ticks_ms()
        log.write(f"0,{mem_alloc()}\n")

        next_sample = time.ticks_add(start_ts, SAMPLE_PERIOD * 1000)

        while True:
            delay = time.ticks_diff(next_sample, time.ticks_ms())
            if delay > 0:
                await asyncio.sleep_ms(delay)

            collect()
            elapsed = time.ticks_diff(time.ticks_ms(), start_ts) // 1000
            log.write(f"{elapsed},{mem_alloc()}\n")
            flush_counter = (flush_counter + 1) % FLUSH_PERIOD
            if not flush_counter:
                log.flush()
            next_sample = time.ticks_add(next_sample, SAMPLE_PERIOD * 1000)


async def main():
    server = http_server.HttpServer()
    connected = wifi.initialize()
    if connected and not machine.reset_cause() == machine.SOFT_RESET:
        import app_base

        app_base.load()

        if get_config(CONF_HTTP_MULTIPART):
            import app_multipart

            app_multipart.load()

        await server.start_socket_server()
        asyncio.create_task(mem_usage())

        while True:
            await asyncio.sleep(1)


asyncio.run(main())
