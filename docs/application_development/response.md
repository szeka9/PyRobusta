# Response Processing

[← Back](index.md)

Response processing controls how route handlers construct HTTP responses.
This includes setting status codes, configuring response headers, serializing response bodies,
and generating streamed or multipart responses.

---

## Table of Contents

* [Response Processing](#response-processing)
  + [Status Codes](#status-codes)
  + [Response Headers](#response-headers)
  + [Cache Control](#cache-control)
  + [Content Types & Serialization](#content-types-serialization)
  + [Streamed Responses](#streamed-responses)
  + [Streamed Multipart Responses](#streamed-multipart-responses)

---

## Status Codes

Route handlers may optionally set the status code of the HTTP response.
If unspecified, the server defaults to HTTP 200. The status code can be overridden
through the `terminate()` method of the HTTP context.

The `terminate()` method updates the response status code and marks the
request as complete, but does not interrupt execution. Route handlers should still return
an appropriate response body.

```
from pyrobusta.protocol.http import HttpEngine

@HttpEngine.route("/app/{resource}", "GET")
def inventory_manager(http_ctx, _):
    resource = http_ctx.path_segment(1)

    if resource == "items":
        # Default HTTP 200
        return "application/json", ["item-1", "item-2", "item-3"]

    elif resource == "version":
        # Default HTTP 200
        return "text/plain", "v0.1.0"

    else:
        # Set 404 status code explicitly
        http_ctx.terminate(404)
        return "text/plain", "Not found"
```

## Response Headers

Response headers and response bodies can be configured through methods exposed by the HTTP context
(`set_response_header()`, `set_response_body()`).
Alternatively, route handlers may return a `(content_type, body)` tuple.

```
import json

from pyrobusta.protocol.http import HttpEngine

config = {"max-items": 5}
items = set(["apple", "orange", "grapes"])

@HttpEngine.route("/inventory/{resource}", "POST")
def inventory_manager(http_ctx, payload):
    resource = http_ctx.path_segment(1)

    if resource == "items":
        if http_ctx.headers.get("content-type") != "text/plain":
            http_ctx.set_response_header(b"accept-post", b"text/plain")
            http_ctx.terminate(415)
            return "text/plain", "Unsupported type"
        if len(items) >= config["max-items"]:
            http_ctx.terminate(400)
            return "text/plain", "Inventory full"
        items.add(payload.decode())
        return "text/plain", ", ".join(items)

    elif resource == "config":
        if http_ctx.headers.get("content-type") != "application/json":
            http_ctx.set_response_header(b"accept-post", b"application/json")
            http_ctx.terminate(415)
            return "text/plain", "Unsupported type"
        payload_json = json.loads(payload)
        if any([key not in config for key in payload_json]) or \
            any([type(value) != type(config[key]) for key, value in payload_json.items()]):
                http_ctx.terminate(400)
                return "text/plain", "Invalid config"
        config.update(payload_json)
        return "application/json", config

    else:
        http_ctx.terminate(404)
        return "text/plain", "Not found"
```

## Cache Control

PyRobusta implements a simple caching policy.
Unless overridden by the application, all HTTP responses include the
header `Cache-Control: no-store`.
Conditional requests and cache validation mechanisms are not supported.
This includes `ETag`, `Last-Modified`,
`If-None-Match`, and `If-Modified-Since`.
This design reduces implementation complexity and avoids additional
filesystem metadata lookups on resource-constrained devices.

## Content Types & Serialization

PyRobusta can automatically serialize a limited set of built-in types and data structures.
Unsupported types must be serialized by the application before being returned as either a string or a bytes-like
object. The following response body types are currently supported:

* `str`
* bytes-like: `bytes`, `bytearray`, `memoryview`
* data structures: `dict`, `tuple`, `list`

For non-streamed responses, the entire response body must exist in memory before it is
transmitted. As a result, the maximum response size is limited by the available heap. In the meantime, a
response buffer has a fixed size depending on the configuration. Internally, response bodies are wrapped
in a `BytesIO` object so that both fixed-size and streamed responses can be written through the same
buffer-oriented interface. Each response body returned by a route handler has a known size, allowing the
content-length header to be filled by the server.

## Streamed Responses

Responses can be streamed in chunks when the application cannot determine the size of the response body in advance.
Such responses must use chunked transfer encoding, indicated by the `Transfer-Encoding` header. With chunked encoding,
the `Content-Length` header must be omitted; instead the size of each chunk must be indicated as the chunks are sent.
The server automatically generates the required chunk metadata.

When chunked transfer encoding is enabled, the server automatically generates the required encoding format.
The application must assign a generator function to `http_ctx.resp_handler`. The server then invokes the generator
when data is ready to be transmitted. The generator may be resumed multiple times until the stream is complete.
The following requirements must be fulfilled by the generator:

1. the generator function must accept a single response buffer argument (`tx`) used to write response data
2. the generator yields `False` after producing a chunk while additional data remains
3. the generator yields `True` exactly once to indicate that the stream is complete
4. the generator verifies the writable capacity of the buffer and
   writes at most that much data to the buffer before yielding

```
# /app.py
import asyncio

from pyrobusta.server import http_server
from pyrobusta.protocol.http import HttpEngine

@HttpEngine.route("/stream", "GET")
def stream(http_ctx, _):

    def generate_chunks(tx):
        for i in range(10):
            data = b"data: chunk %d\n\n" % i
            written = 0
            while written < len(data):
                to_write = tx.capacity - tx.size()
                # Defensive check; buffer should never be full here
                if not to_write:
                    raise BufferError()
                tx.write(data[written : written + to_write])
                written += to_write
                yield False
        yield True

    http_ctx.set_response_header(b"transfer-encoding", b"chunked")
    http_ctx.set_response_header(b"content-type", b"text/event-stream")
    http_ctx.resp_handler = generate_chunks

async def main():
    server = http_server.HttpServer()
    await server.start_socket_server()
    while True:
        await asyncio.sleep(1)
```

```
$ curl 192.168.1.101/stream
data: chunk 0

data: chunk 1

data: chunk 2

...

data: chunk 9
```

## Streamed Multipart Responses

Multipart responses allow a single HTTP response to contain multiple independently typed payloads,
each with its own headers and body. Similar to streamed responses, PyRobusta uses response producer
functions to generate multipart response parts on demand. Because the total response size is not known
in advance, the server automatically uses chunked transfer encoding for multipart responses. It is
explicitly enabled in the example below for completeness.

Routes producing streamed multipart responses must satisfy the following requirements:

1. the route must return a tuple containing the multipart content type and a callable response producer
2. the response producer must return a tuple containing the content type and payload of each part
3. after producing the final part, the response producer must return None

```
# /app.py
import asyncio

from pyrobusta.server import http_server
from pyrobusta.protocol.http import HttpEngine

def multipart_response(num_responses, part_size):
    i = 0
    def response_producer():
        nonlocal i
        i += 1
        if i > num_responses:
            return None
        return "text/plain", b"X" * part_size
    return response_producer

@HttpEngine.route("/multipart", "GET")
def multipart_handler(http_ctx, _):
    http_ctx.set_response_header(b"transfer-encoding", b"chunked")
    part_count = int(http_ctx.headers.get("x-part-count", 1))
    part_size = int(http_ctx.headers.get("x-part-size", 1024))
    return "multipart/form-data", multipart_response(part_count, part_size)

async def main():
    server = http_server.HttpServer()
    await server.start_socket_server()
    while True:
        await asyncio.sleep(1)
```

Try the `X-Part-Count` and `X-Part-Size` headers to arbitrarily configure the response size.

```
$ curl -H "X-Part-Count: 3" -H "X-Part-Size: 10" 192.168.1.101/multipart
--pyrobusta-boundary
content-type:text/plain

XXXXXXXXXX
--pyrobusta-boundary
content-type:text/plain

XXXXXXXXXX
--pyrobusta-boundary
content-type:text/plain

XXXXXXXXXX
--pyrobusta-boundary--
```

---

PyRobusta v0.7.0 Web Server
