# Logging & Error Handling

[← Back](index.md)

This page describes how the server provides logging with different levels of verbosity
and handles HTTP status codes for client and server errors, including exceptions raised by applications.

---

## Table of Contents

* [Logging & Error Handling](#logging-error-handling)
  + [Logging](#logging)
  + [Client Errors (4xx)](#client-errors-4xx)
  + [Server Errors (5xx)](#server-errors-5xx)
  + [Exception Handling](#exception-handling)

---

## Logging

The server provides built-in logging constructs implemented by the `pyrobusta.utils.logging`
module. The logging module supports several log levels, controlled by the `log_level` server
configuration. `log_level` can be set to one of `error`, `warning`, `info`, or `debug`, listed in increasing
order of verbosity. Selecting a log level enables logging for that level and all less verbose levels.
For example, setting `log_level` to `info` enables `info`, `warning`, and `error` messages.

Logging methods expect a mandatory format string as the first positional argument,
followed by optional positional arguments substituted in the format string.

```python
import asyncio

from pyrobusta import application
from pyrobusta.utils import logging


async def main():
  await application.run()
  logging.info("%s: %s", __name__, "the application started")
  while True:
    await asyncio.sleep(1)

asyncio.run(main())
```

```log
29972 INFO pyrobusta.application: connected, ip=[192.168.1.101]
29983 INFO pyrobusta.server.http_server: 1 connection(s) allowed
30029 INFO pyrobusta.server.http_server: started
30041 INFO __main__: the application started
```

## Client Errors (4xx)

As described in the [Response Handling](./response.md#status-codes) guide, route
handlers can set the status codes directly with the `terminate` method of the HTTP
context. Invalid requests should be rejected by the application with a 4xx status
code. The specific status code is application-specific.

```python
@HttpEngine.route("/app/action", "POST")
def handler(http_ctx, _):
    content_type = http_ctx.headers.get("content-type")
    if content_type != "application/json":
      http_ctx.terminate(415)
      return "text/plain", "Unsupported media"
    # <rest of the application route>
```

The application must use one of the following status codes supported by PyRobusta:

| Status Code | HTTP Status |
| --- | --- |
| 400 | Bad Request |
| 401 | Unauthorized |
| 403 | Forbidden |
| 404 | Not Found |
| 405 | Method Not Allowed |
| 408 | Request Timeout |
| 413 | Content Too Large |
| 415 | Unsupported Media Type |

## Server Errors (5xx)

5xx status codes indicate errors preventing the server from processing a valid request.
The following list of 5xx status codes are supported by PyRobusta:

| Status Code | HTTP Status |
| --- | --- |
| 500 | Internal Server Error |
| 503 | Service Unavailable |
| 505 | Version Not Supported |

## Exception Handling

Applications may raise exceptions to signal a failure. Uncaught exceptions are
automatically mapped to the 500 status code sent in the response.

Additionally, when the server catches an exception raised by the application,
it logs an error message.

```python
@HttpEngine.route("/app/action", "POST")
def handler(http_ctx, _):
    # [...]
    raise RuntimeError("failed to execute action")
    # [...]
```

```log
2287169 INFO pyrobusta.application: already connected ip=[192.168.1.101]
2287179 INFO pyrobusta.server.http_server: 1 connection(s) allowed
2287222 INFO pyrobusta.server.http_server: started
[...]
2292844 ERROR pyrobusta.protocol.http.run: error=[failed to execute action]
```

---

PyRobusta v0.8.0 Web Server
