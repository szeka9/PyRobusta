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

```python
# /app.py
import asyncio

from pyrobusta import application
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
    await application.run()
    while True:
        await asyncio.sleep(1)
```

```python
# /boot.py
# This file is executed on every boot

import asyncio
import machine
import app

if machine.reset_cause() != machine.SOFT_RESET:
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

PyRobusta v0.8.0 Web Server
