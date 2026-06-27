# HTTP state machine parser

[http.py](../../src/pyrobusta/protocol/http.py) implements a finite state machine (FSM) whose states
are represented by handler functions. Each state consumes as much available data as necessary
to make progress, or returns control to the event loop until additional input becomes available.

In general, states are not required to transition to a terminal state if a request is incomplete.
Instead, states return control to the asyncio event loop, which drives subsequent invocations of the
state machine based on socket readiness. The state machine may be terminated by the surrounding coroutine in
the case of a connection timeout or transport error, separating HTTP protocol semantics from transport-level
I/O scheduling concerns.

The state machine can be decomposed into four sub-FSMs with a common terminal state. Each sub-FSM eventually
transitions to `terminal_st`, which serves as a finalization state responsible for emitting HTTP headers required
for interoperability, such as connection persistence and cache-control directives. The terminal state can only be reached
by calling `HttpEngine.terminate()`, which requires a valid HTTP status code. The method may be invoked by the user application, the coroutine responsible for socket handling, or the state machine itself.

The state machine is associated with a single HTTP connection and maintains dedicated request and response stream buffers.
For persistent connections, the state machine instance is reset and reused for each request received on the connection.
The `HttpConnection` class is responsible for advancing the state machine, scheduling socket I/O through asyncio's `StreamReader` and `StreamWriter` interfaces, and reusing the state machine across persistent connections.

## HTTP Request Line and Header Parsing
```mermaid
stateDiagram-v2

    [*] --> start_parser

    start_parser --> parse_request_line_st: rx.size() > 0
    start_parser --> start_parser: empty buffer

    parse_request_line_st --> parse_headers_st: valid request line parsed
    parse_request_line_st --> parse_request_line_st: incomplete line
    parse_request_line_st --> terminal_st: 405/505 terminate

    parse_headers_st --> route_request_st: headers complete
    parse_headers_st --> parse_headers_st: waiting for \r\n\r\n
    parse_headers_st --> terminal_st: invalid headers (host missing etc.)
```

## Routing and Body Strategy Selection
```mermaid
stateDiagram-v2

    route_request_st --> handle_route_st: route + no payload

    route_request_st --> recv_payload_st: content-length body
    route_request_st --> recv_chunk_size_st: chunked encoding
    route_request_st --> start_multipart_parser_st: multipart body

    route_request_st --> fs_retrieve_st: GET/HEAD fallback file server

    route_request_st --> terminal_st: 404 no route
    route_request_st --> terminal_st: 405 method not allowed
    route_request_st --> terminal_st: 204 OPTIONS

    recv_payload_st --> handle_route_st: full body received
    recv_payload_st --> recv_payload_st: waiting for content-length

    recv_chunk_size_st --> recv_chunk_st: size parsed
    recv_chunk_size_st --> recv_chunk_size_st: waiting for chunk size

    recv_chunk_st --> handle_route_st: chunk complete
    recv_chunk_st --> recv_chunk_st: waiting for full chunk
```

## Application Execution and Response Generation
```mermaid
stateDiagram-v2

    handle_route_st --> handle_route_st: application processing

    handle_route_st --> recv_chunk_size_st: more chunked data expected

    handle_route_st --> terminal_st: default termination (200 OK)

    handle_route_st --> terminal_st: 2XX/4XX/5XX (terminated by application)

    fs_retrieve_st --> terminal_st: 200 file served
    fs_retrieve_st --> terminal_st: 403 forbidden
    fs_retrieve_st --> terminal_st: 404 file missing
```

## Multipart Request Processing
```mermaid
stateDiagram-v2

    start_multipart_parser_st --> parse_boundary_st: boundary validated

    parse_boundary_st --> parse_complete_part_st: boundary detected
    parse_boundary_st --> parse_boundary_st: waiting for boundary

    parse_complete_part_st --> parse_boundary_st: more parts remain
    parse_complete_part_st --> terminal_st: 200 OK (final part processed - default)
    parse_complete_part_st --> terminal_st: 2XX/4XX/5XX (terminated by application)
```

## State Machine Termination
```mermaid
stateDiagram-v2

    terminal_st --> [*]: finalize headers (keep-alive connection, cache policy)
```

## Connection Lifecycle
```mermaid
flowchart LR

    HttpConnection --> id1[run parser]
    id1[run parser] --> id2[terminate state machine]
    id2[terminate state machine] --> id3[Connection: close]
    id2[terminate state machine] --> id4[Connection: keep-alive]
    id3[Connection: close] --> id5[Destroy Parser]
    id4[Connection: keep-alive] --> id6[Reset Parser]
    id6[Reset Parser] --> id1[run parser]
```