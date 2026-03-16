# This file is executed on every boot (including wake-boot from deepsleep)
from pyrobusta.con import wifi

wifi.initialize()

#import esp
#esp.osdebug(None)
#import webrepl
#webrepl.start()
