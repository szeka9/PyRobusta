# Device Setup

Use [mpremote](https://docs.micropython.org/en/latest/reference/mpremote.html) to access your device over a serial connection.\
You can install mpremote via pip. It is also included in the project's requirements.txt

```bash
python3 -m venv venv
source venv/bin/activate
python3 -m pip install -r requirements.txt
```

After installing mpremote, check if you can connect to your device:
```bash
$ mpremote a1 soft-reset repl
Connected to MicroPython at /dev/ttyACM1
Use Ctrl-] or Ctrl-x to exit this shell
>
MicroPython v1.27.0 on 2025-12-09; ESP32C3 module with ESP32C3
Type "help()" for more information.
>>> 
```

# Connect to Wi-Fi

During the initial setup, you’ll need to connect your device to a Wi-Fi network in order to install PyRobusta using the mip package manager.\
After connecting to your device with mpremote, run the following script:

```python
from network import WLAN, STA_IF
from time import sleep

ssid = "<your-wifi-name>"
password = "<your-password>"

sta_if = WLAN(STA_IF)
sta_if.active(True)
sta_if.connect(ssid, password)

timeout = 30
while timeout > 0:
    if sta_if.isconnected():
        ip = sta_if.ifconfig()[0]
        print(f"connected, IP={ip}")
        break
    sleep(1)
    timeout -= 1

if sta_if.isconnected():
    print(sta_if.ifconfig()[0])
else:
    print("connection failed")
```
Alternatively, follow the [development guide](./development.md) to build and deploy directly from source without requiring a network connection.

# Automatic Connection on Boot

Once PyRobusta is installed, the server automatically initializes Wi-Fi in station mode, requiring a correct SSID and password
of a Wi-Fi network. Override `wifi_ssid` and `wifi_password` in the configuration stored in [pyrobusta.env](./application_development/configuration.md).
The server will skip Wi-Fi connection if the credentials are missing, allowing the user application to manage network connectivity.


```python
# boot.py
import machine
from pyrobusta import application

async def main():
    await application.run()
    while True:
        await asyncio.sleep(1)

if machine.reset_cause() != machine.SOFT_RESET:
    asyncio.run(main())
```

Upload boot.py to your device with mpremote:
```bash
$ mpremote a1 cp boot.py :/boot.py
```
