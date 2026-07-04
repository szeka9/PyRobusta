# Getting Started

[← Back](index.md)

This page provides practical examples for using your server.

---

## Table of Contents

* [Getting Started](#getting-started)
  + [Demo Application](#demo-application)
  + [Deployment with mpremote](#deployment-with-mpremote)

---

## Demo Application

The following application demonstrates the basic structure of a PyRobusta application, including route registration,
response generation, and server initialization. The application implements a simple HTTP API that returns the application version.
The example includes boot.py, which starts the application, and app.py, which registers routes and starts the HTTP server.

```
import asyncio

from pyrobusta.server import http_server
from pyrobusta.protocol.http import HttpEngine

APP_VERSION = "v0.1.0"

@HttpEngine.route("/version", "GET")
def version(http_ctx, _):
    if http_ctx.headers.get("accept") == "application/json":
        return "application/json", {
            "version": APP_VERSION
        }

    return "text/plain", f"{APP_VERSION}\n"

async def main():
    server = http_server.HttpServer()
    server.start_socket_server()

    while True:
        await asyncio.sleep(1)
```

```
# /boot.py
# This file is executed on every boot

import machine
from os import listdir

from pyrobusta.connectivity import wifi

connected = wifi.initialize()
if connected and not machine.reset_cause() == machine.SOFT_RESET:
    if "app.py" in listdir():
        import app

        asyncio.run(app.main())
```

In the example, `boot.py` conditionally starts the server when no REPL session is active.
This allows `mpremote` to connect after a soft reset and upload files during development.

## Deployment with mpremote

Perform a soft reset and upload app.py and boot.py using `mpremote`.

```
$ mpremote a0 soft-reset
$ mpremote a0 cp app.py :/app.py
$ mpremote a0 cp boot.py :/boot.py
```

Perform a hard reset to start the application and connect to the REPL.

```
$ mpremote a0 reset repl
Connected to MicroPython at /dev/ttyACM0
...
[INFO] pyrobusta.con.wifi: network b'Home-Wi-Fi' found!
[INFO] pyrobusta.con.wifi: connected, available at 192.168.1.101
[WARN] pyrobusta.server.http_server.init_pools: low-memory mode with reduced buffer size
[INFO] pyrobusta.server.http_server.init_pools: 2 connection(s) allowed
[INFO] pyrobusta.server.http_server: started

# You can now reach the device at 192.168.1.101 (replace with your IP)
# Press Ctrl-x to exit
```

Use curl to test the application.

```
$ curl "http://192.168.1.101/version"
v0.1.0

$ curl -H "Accept: application/json" "http://192.168.1.101/version"
{"version": "v0.1.0"}
```

---

PyRobusta v0.7.0 Web Server
