# This file is executed on every boot (including wake-boot from deepsleep)
import machine
from os import listdir

from pyrobusta.con import wifi

connected = wifi.initialize()
if connected and not machine.reset_cause() == machine.SOFT_RESET:
    if "app.py" in listdir():
        import app

        app.main()
