# Introduction

[← Back](index.md)

This page provides practical examples for using your server.

---

## Table of Contents

* [Introduction](#introduction)
  + [Demo Application](#demo-application)
  + [Deployment with mpremote](#deployment-with-mpremote)

---

## Demo Application

The following application demonstrates common use cases for handling headers, status codes, query parameters, and wildcard routes.

1. **/version** returns the version of the application.

   The server version can optionally be included in the response by setting the detailed query parameter to true.
2. **/app/version** or **/server/version** returns the designated version string, handled by a single route handler with a wildcard URL.

```
# /app.py

import asyncio

from pyrobusta.server import http_server
from pyrobusta.protocol.http import HttpEngine
from pyrobusta.utils.config import PYROBUSTA_VERSION

APP_VERSION = "v0.0.1"

@HttpEngine.route("/version", "GET")
def version(http_ctx, _):
    include_server_version = False

    if http_ctx.query:
        is_detailed = http_ctx.get_query_param(
            "detailed", default="false"
        ).lower()

        if is_detailed not in ("true", "false"):
            http_ctx.terminate(400)
            return "text/plain", "Invalid query"

        include_server_version = is_detailed == "true"

    if http_ctx.headers.get("accept") == "application/json":
        version_dict = {"app_version": APP_VERSION}
        if include_server_version:
            version_dict["server_version"] = PYROBUSTA_VERSION
        return "application/json", version_dict

    version_text = f"app_version: {APP_VERSION}\n"
    if include_server_version:
        version_text += f"server_version: {PYROBUSTA_VERSION}\n"
    return "text/plain", version_text

@HttpEngine.route("/{app_or_server}/version", "GET")
def version(http_ctx, _):
    resource = http_ctx.path_segment(0)

    if resource not in ("app", "server"):
        http_ctx.terminate(404)
        return "text/plain", "Not found"

    version_string = APP_VERSION if resource == "app" else PYROBUSTA_VERSION

    if http_ctx.headers.get("accept") == "application/json":
        return "application/json", {"version": version_string}

    return "text/plain", f"{version_string}\n"

async def main():
    server = http_server.HttpServer()
    asyncio.create_task(server.start_socket_server())
    while True:
        await asyncio.sleep(1)
```

```
# /boot.py

# This file is executed on every boot (including wake-boot from deepsleep)
import machine
from os import listdir

from pyrobusta.connectivity import wifi

connected = wifi.initialize()
if connected and not machine.reset_cause() == machine.SOFT_RESET:
    if "app.py" in listdir():
        import app

        asyncio.run(app.main())
```

## Deployment with mpremote

Perform a soft reset and upload app.py and boot.py using mpremote.

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
app_version: v0.0.1

$ curl "http://192.168.1.101/version?detailed=True"
app_version: v0.0.1
server_version: v0.5.0

$ curl -H "Accept: application/json" "http://192.168.1.101/version?detailed=True"
{"server_version": "v0.5.0", "app_version": "v0.0.1"}

$ curl "http://192.168.1.101/app/version"
v0.0.1

$ curl "http://192.168.1.101/server/version"
v0.5.0

$ curl -H "Accept: application/json" "http://192.168.1.101/server/version"
{"version": "v0.5.0"}

$ curl  192.168.1.101/application/version
Not found
```

---

PyRobusta v0.7.0 Web Server
