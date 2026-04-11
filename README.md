# PyRobusta

A lightweight HTTP server library for MicroPython designed for constrained embedded systems.

## HTTP features
- Routing decorators
- Fixed-size, configurable request/response buffers
- Multipart request and response handling
- Chunked transfer decoding for streamed request bodies
- Bounded-copy memory footprint
- Finite-state-machine parser with linear sliding buffer
- Robust byte-stream handling
- Query parameter parsing with percent encoding support
- TLS support

# Installation

Use the mip package manager to install PyRobusta on your MicroPython-installed device.\
The bare minimum requirement is 40KB of free heap, however, it is recommended to select\
boards with more SRAM for usability and stability. The ESP32-C3 is a recommended entry-level\
board leaving a user-friendly amount of memory after installing PyRobusta.

If required, use the below script to connect to a Wi-Fi station in advance.
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

Install and start PyRobusta by following the below steps. For more advanced usage,\
check the included documentation reachable from the home page served by your device.

```python
# Download latest version of PyRobusta
import mip
mip.install("github:szeka9/PyRobusta")

# Install assets
from pyrobusta.utils.assets import install_www
install_www()

# Start the server
import asyncio
from pyrobusta.server.http_server import HttpServer

async def main():
    server = HttpServer()
    asyncio.create_task(server.start_socket_server())
    while True:
        await asyncio.sleep(1)

asyncio.run(main())
```
Open a browser and type your device's IP in the address bar. You should be greeted\
by the default home page.

![image info](./docs/img/home_page.png)

For fine-tuning heap usage, check the [dimensioning guide](./docs/dimensioning/http_dimensioning.md)\
and [configuration settings](./docs/configuration.md).

# Development

Check the provided development guide to create and deploy custom builds\
to your device: [development guide](./docs/development.md)
