# Routing

[← Back](index.md)

Routing maps incoming HTTP requests to application-defined route handlers.
This page describes how routes are defined, how route handlers receive requests, and how wildcard routes
can be used to match dynamic URL paths.

---

## Table of Contents

* [Routing](#routing)
  + [Route Definitions](#route-definitions)
  + [Route Handlers](#route-handlers)
  + [Wildcard Routes](#wildcard-routes)
  + [Route Registration & Deregistration](#route-registration-deregistration)

---

## Route Definitions

Routes map HTTP requests to server-side handler functions that
process requests and manage resources. Similar to common web frameworks, PyRobusta
utilizes function decorators to map handler functions to URL paths. A route handler
can only be mapped to a single URL path and HTTP method. The same URL path may be
associated with multiple route handlers provided that each handler uses a different
HTTP method.

```
from pyrobusta.protocol.http import HttpEngine

@HttpEngine.route("/app/resource", "GET")
def get_handler(http_ctx, _):
    return "text/plain", "resource content\n"

@HttpEngine.route("/app/resource", "POST")
def post_handler(http_ctx, payload):
    return "text/plain", "payload processed\n"
```

## Route Handlers

In PyRobusta, a route handler is a synchronous function registered to a
specific URL path and HTTP method. PyRobusta invokes a route handler whenever it receives a
request whose URL path and HTTP method match the registered route. Route handlers must accept
exactly two positional arguments:

* HTTP context (`HttpEngine` class)
* Request body (`memoryview`)

### HTTP Context

The HTTP context is an instance of the `HttpEngine` class that exposes the
public API used to inspect requests and construct responses. The HTTP context provides public
methods and attributes that enable user applications to process headers and structure responses.
By convention, non-public attributes and methods are prefixed with an underscore.

Apart from the public API, the HTTP context also encapsulates the state associated with the current
request and response exchange. Internally, the HTTP context ensures protocol correctness and assists
with request routing.

### Request Body

Depending on the request type, the body argument may contain either the complete
request body or a partial payload chunk. Partial request bodies are passed to route handlers
when the request uses multipart encoding or chunked transfer encoding, with each chunk of the payload
fed incrementally to the route handler. Such request processing is documented in the
[Request Processing](./request.md#streamed-requests) guide.

## Wildcard Routes

Wildcard routes use placeholders in one or more segments of a URL path.
These placeholders match varying path values, allowing multiple URL paths to be mapped to
a single handler function. A placeholder matches a single path segment by default. Alternatively,
a placeholder can match multiple segments by using the `:path` suffix. For example:

`/path/to/{resource:path}`

Placeholders that match multiple path segments are only allowed at the end of a route. For example,
`/path/{to:path}/resource` is disallowed because it would result in ambiguous route resolution.

```
from pyrobusta.protocol.http import HttpEngine

sensor_values = {
    "dht22": {
        "temperature_c": 22,
        "rel_hum": 45
    }
}

@HttpEngine.route("/sensors/{name}/values/{value_name}", "GET")
def wildcard_url_handler(http_ctx, _):
    sensor_name = http_ctx.path_segment(1)
    sensor_value = http_ctx.path_segment(3)

    if sensor_name not in sensor_values:
        http_ctx.terminate(404)
        return "text/plain", "Not found"

    values = sensor_values[sensor_name]

    if sensor_value not in values:
        http_ctx.terminate(404)
        return "text/plain", "Not found"

    return "text/plain", str(values[sensor_value])
```

## Route Registration & Deregistration

By convention, user applications should use decorators
to register route handlers in most cases. This approach ensures that routes are registered
during application initialization, and routes remain available for the lifetime of the application.
The public API exposed by `HttpEngine` allows route registration and deregistration
during an application's lifecycle, enabling applications to dynamically expose or
remove functionality at runtime.

```
from pyrobusta.protocol.http import HttpEngine

sensor_values = {
    "dht22": {
        "temperature_c": 22,
        "rel_hum": 45
    },
    "ldr": {
        "illuminance_lx": 50
    }
}

def dht22_handler(http_ctx, _):
    return "application/json",  sensor_values["dht22"]

def ldr_handler(http_ctx, _):
    return "application/json", sensor_values["ldr"]

@HttpEngine.route("/sensor/{name}/enabled", "PUT")
def enable_sensor(http_ctx, enabled):
    sensor_name = http_ctx.path_segment(1)

    if sensor_name not in sensor_values:
        http_ctx.terminate(404)
        return "text/plain", "Not found"

    if enabled.decode().lower() not in ("true", "false"):
        http_ctx.terminate(400)
        return "text/plain", "Invalid value"

    is_enabled = enabled.decode().lower() == "true"

    if sensor_name == "dht22":
        route_handler = dht22_handler

    elif sensor_name == "ldr":
        route_handler = ldr_handler

    if is_enabled:
        HttpEngine.register(f"/sensor/{sensor_name}/value", route_handler, "GET")
    else:
        HttpEngine.deregister(f"/sensor/{sensor_name}/value", "GET")

    return "text/plain", "OK"
```

---

PyRobusta v0.7.0 Web Server
