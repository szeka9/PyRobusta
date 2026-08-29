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

Perform a soft reset and upload app.py and boot.py using `mpremote`:

```bash
$ mpremote connect /dev/ttyACM1 soft-reset
$ mpremote connect /dev/ttyACM1 cp app.py :/app.py
$ mpremote connect /dev/ttyACM1 cp boot.py :/boot.py
```

Perform a hard reset to start the application and connect to the REPL:

```bash
$ mpremote connect /dev/ttyACM1 reset sleep 1 repl
Connected to MicroPython at /dev/ttyACM1
Use Ctrl-] or Ctrl-x to exit this shell
[...]
2711 INFO pyrobusta.application: connected, ip=[192.168.1.101]
2732 INFO pyrobusta.server.http_server: 4 connection(s) allowed
2762 INFO pyrobusta.server.http_server: started

# You can now reach the device at the indicated IP address
# Press Ctrl-x to exit
```

Use curl to test the application:

```bash
$ curl "http://192.168.1.101/version"
v0.1.0

$ curl -H "Accept: application/json" "http://192.168.1.101/version"
{"version": "v0.1.0"}
```

---

PyRobusta v0.9.0 Web Server
