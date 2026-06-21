# HTTP state machine parser

[http.py](../../src/pyrobusta/protocol/http.py) implements a continuation passing parser using a
finite state machine (FSM). Each state consumes available sufficient data to make progress or explicitly
suspend until more data arrives.

In general, states are not required to transition to a terminal state if a request is incomplete.
Instead, states return control to the asyncio event loop, which drives subsequent invocations of the
state machine based on socket readiness. The state machine may be terminated by the surrounding coroutine in
the case of a session timeout or transport error. This is a deliberate architectural decision to separate HTTP
protocol semantics from transport-level I/O scheduling concerns.

The state machine can be decomposed to four sub-FSMs, depicted by the below diagrams. The state machine applies
to a single HTTP session with a dedicated request and response stream buffer.


## HTTP Request Line and Header Parsing
```mermaid
stateDiagram-v2

    [*] --> start_parser

    start_parser --> parse_request_line_st: rx.size() > 0
    start_parser --> start_parser: empty buffer

    parse_request_line_st --> parse_headers_st: valid request line parsed
    parse_request_line_st --> parse_request_line_st: incomplete line
    parse_request_line_st --> [*]: 405/505 terminate

    parse_headers_st --> route_request_st: headers complete
    parse_headers_st --> parse_headers_st: waiting for \r\n\r\n
    parse_headers_st --> [*]: invalid headers (host missing etc.)
```

## Routing and Body Strategy Selection
```mermaid
stateDiagram-v2

    route_request_st --> handle_route_st: route + no payload

    route_request_st --> recv_payload_st: content-length body
    route_request_st --> recv_chunk_size_st: chunked encoding
    route_request_st --> start_multipart_parser_st: multipart body

    route_request_st --> fs_retrieve_st: GET/HEAD fallback file server

    route_request_st --> [*]: 404 no route
    route_request_st --> [*]: 405 method not allowed
    route_request_st --> [*]: 204 OPTIONS

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

    handle_route_st --> handle_route_st: execute handler / process request

    handle_route_st --> recv_chunk_size_st: more chunked data expected

    handle_route_st --> generate_multipart_response_st: multipart response

    handle_route_st --> [*]: 200 OK (default completion)

    fs_retrieve_st --> [*]: 200 file served
    fs_retrieve_st --> [*]: 403 forbidden
    fs_retrieve_st --> [*]: 404 file missing

    generate_multipart_response_st --> [*]: 200 headers set + stream ready
```

## Multipart Request Processing
```mermaid
stateDiagram-v2

    start_multipart_parser_st --> parse_boundary_st: boundary validated

    parse_boundary_st --> parse_complete_part_st: boundary detected
    parse_boundary_st --> parse_boundary_st: waiting for boundary

    parse_complete_part_st --> parse_boundary_st: more parts remain
    parse_complete_part_st --> [*]: final part processed (200)
```