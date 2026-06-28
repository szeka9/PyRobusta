# Request Processing

[← Back](index.md)

This page describes how route handlers receive and process incoming HTTP requests.

---

## Table of Contents

* [Request Processing](#request-processing)
  + [Query Parameters](#query-parameters)
  + [Request Headers](#request-headers)
  + [Request Bodies](#request-bodies)
  + [Streamed Requests](#streamed-requests)
  + [Multipart Requests](#multipart-requests)

---

## Query Parameters

Handler functions take an HTTP context and payload as arguments.
While handler functions cannot define additional arguments, extra input can be provided
through query parameters. Query parameters appear after the path component of a URL and
are introduced by a question mark (?), for example:

`http://192.168.1.101/path/to/resource?param-key=param-value`

Query parameters use the same encoding rules as the `application/x-www-form-urlencoded` format.
Multiple query parameters are separated by the ampersand (&). Percent-encoded characters
(for example, %2F representing /) are decoded automatically by the server.

Query parameters can be retrieved using the `get_query_param()` function, which accepts two
arguments: the name of the key and an optional default value. The function returns a string
that can be further processed by the application.

```
from pyrobusta.protocol.http import HttpEngine

@HttpEngine.route("/app/resource", "GET")
def query_param_handler(http_ctx, _):
    # Handler for /app/resource?detailed=true/false

    is_detailed = False

    if http_ctx.query:
        is_detailed = http_ctx.get_query_param(
            "detailed", default="false"
        ).lower()

        if is_detailed not in ("true", "false"):
            http_ctx.terminate(400)
            return "text/plain", "Invalid query"

    resource = "resource content\n"
    if is_detailed:
        resource = "detailed " + resource

    return "text/plain", resource
```

## Request Headers

Headers received in a request are available in the `headers` attribute of the HTTP context.
The `headers` attribute is a dictionary of key-value pairs. Header names and values are exposed as strings.
As a convenience, the `Content-Length` header is automatically converted to an integer because it is frequently used for
payload size calculations. Headers are normalized to lower case, so the key `"Content-Length"` is equivalent to the key
`"content-length"`.

Request headers must contain only a subset of US-ASCII characters:

* header names are restricted to letters, digits, hyphens, and underscores
* header values are limited to US-ASCII characters, excluding control characters

```
from pyrobusta.protocol.http import HttpEngine

@HttpEngine.route("/app", "GET")
def app(http_ctx, _):
    if http_ctx.headers.get("accept", "*/*") == "text/plain":
        return "text/plain", "App response\n"
    elif http_ctx.headers["accept"] == "application/json":
        return "application/json", {"response": "App response"}
    raise ValueError("Unsupported accept header")
```

## Request Bodies

A request payload is passed as the second positional argument of the
route handler. Unless the request uses streaming or multipart encoding, the payload
is provided as a memoryview to avoid unnecessary memory allocations. Deserialization must be done
by the user application.

```
import json

from pyrobusta.protocol.http import HttpEngine

@HttpEngine.route("/app", "GET")
def app(http_ctx, _):
    return "text/plain", "GET request without payload"

@HttpEngine.route("/app", "POST")
def app(http_ctx, payload):
    data = json.loads(bytes(payload))
    return "text/plain", "POST request with payload"
```

## Streamed Requests

PyRobusta supports streaming requests by processing individual
chunks of the request body as they are received. To enforce bounded memory usage,
request chunks are processed individually by calling registered route handlers
for each chunk received. As a result, the application must process the request body
incrementally rather than assuming the full payload is available at once.

```
import pyrobusta.server.http_server as http_server
from pyrobusta.protocol.http import HttpEngine
from pyrobusta.utils.helpers import normalize_path

@HttpEngine.route("/app/chunks", "POST")
def upload_chunks(http_ctx, payload: bytes):
    """
    Route handler for demonstrating chunked transfer encoding.
    """
    if not http_ctx.is_chunked():
        http_ctx.terminate(400)
        return "text/plain", "Bad request"

    if payload:
        # Wait for more chunks before setting response status
        with open(normalize_path("/tmp/chunks.txt"), "ab") as f:
            f.write(payload)
        return

    # Last (empty) chunk received
    http_ctx.terminate(201)
    return "text/plain", "OK"

async def main():
    server = http_server.HttpServer()
    asyncio.create_task(server.start_socket_server())
    while True:
        await asyncio.sleep(1)
```

## Multipart Requests

Multipart requests allow clients to send composite payloads with
the option of varying content metadata or multiple resources in a single request.
Similar to streamed requests, multipart requests are processed one part at a time.
The route handler is invoked once for each part. Unlike regular request bodies, multipart
parts are parsed by the server before being passed to the application. Peprocessed parts
consist of headers (dictionary) and the raw part body (bytes), passed as a tuple.

**Multipart state tracking**
The HTTP context exposes the boolean attributes
`mp_is_first` and
`mp_is_last`
to identify the first and final part of a multipart request. This allows stateful processing
of multiple parts belonging to the same request.

```
from os import listdir, remove, rename, mkdir

import pyrobusta.server.http_server as http_server
from pyrobusta.protocol.http import HttpEngine
from pyrobusta.utils.helpers import normalize_path

@HttpEngine.route("/app/parts", "POST")
def handle_parts(http_ctx, payload: tuple):
    """
    Route handler for demonstrating multipart processing.
    """
    if not http_ctx.is_multipart():
        http_ctx.terminate(400)
        return "text/plain", "Bad request"

    part_headers, part_body = payload

    tmp_dir = normalize_path("/tmp")
    tmp_path = normalize_path("/tmp/parts.txt")
    target_path = normalize_path("/www/user_data/parts.txt")

    # Clean stale partial uploads
    if http_ctx.mp_is_first:
        if not "tmp" in listdir(normalize_path("/")):
            mkdir(tmp_dir)
        if "parts.txt" in listdir(tmp_dir):
            remove(tmp_path)

    with open(tmp_path, "ab") as f:
        f.write(part_body)

    # Finalize uploads
    if http_ctx.mp_is_last:
        rename(tmp_path, target_path)
        http_ctx.terminate(201)
        return "text/plain", "OK"

async def main():
    server = http_server.HttpServer()
    asyncio.create_task(server.start_socket_server())
    while True:
        await asyncio.sleep(1)
```

---

PyRobusta v0.7.0 Web Server
