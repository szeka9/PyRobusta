# This file is executed on every boot (including wake-boot from deepsleep)
import asyncio
import machine
from os import listdir

if not machine.reset_cause() == machine.SOFT_RESET:
    if "app.py" in listdir():
        import app

        asyncio.run(app.main())
