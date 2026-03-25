"""
Module is responsible for webserver state machine,
with partial guarantees on RFC compliance.
"""

from json import dumps
from io import BytesIO
from os import stat

from ..utils.config import get_config


class HeaderParsingError(ValueError):
    """Exception for errors occurring while parsing HTTP/MIME headers"""

    pass


class ServerBusyError(RuntimeError):
    """Exception for applications to indicate busy state"""

    pass


class HttpEngine:
    """
    HTTP protocol parser state machine
    - provides an adapter/routing layer
    - supports multipart request and response handling
    - resolves static resources by returning a stream objects (FileIO)
    """

    __slots__ = (
        "state",
        "status_code",
        "response_headers",
        "version",
        "headers",
        "method",
        "url",
        "content_length_cnt",
        "mp_boundary",
        "mp_first_part",
        "mp_last_part",
        "mp_delimiter",
        "mp_closing_delimiter",
    )

    ENDPOINTS = []  # (endpoint, callback, method)
    RESP_HEADERS = (
        200,
        b"200 OK",
        204,
        b"204 No Content",
        400,
        b"400 Bad Request",
        404,
        b"404 Not Found",
        405,
        b"405 Method Not Allowed",
        408,
        b"408 Request Timeout",
        413,
        b"413 Content Too Large",
        500,
        b"500 Internal Server Error",
        503,
        b"503 Service Unavailable",
        505,
        b"505 Version Not Supported",
    )
    CONTENT_TYPES = (
        b"raw",
        b"application/octet-stream",
        b"html",
        b"text/html",
        b"css",
        b"text/css",
        b"js",
        b"application/javascript",
        b"json",
        b"application/json",
        b"ico",
        b"image/x-icon",
        b"jpeg",
        b"image/jpeg",
        b"jpg",
        b"image/jpeg",
        b"png",
        b"image/png",
        b"txt",
        b"text/plain",
        b"gif",
        b"image/gif",
    )

    ASCII = "ascii"
    CONTENT_LENGTH = "content-length"

    DELETE = b"DELETE"
    GET = b"GET"
    HEAD = b"HEAD"
    OPTIONS = b"OPTIONS"
    POST = b"POST"
    PUT = b"PUT"
    METHODS = (DELETE, GET, HEAD, OPTIONS, POST, PUT)
    SUPPORTED_VERSIONS = (b"HTTP/1.1", b"HTTP/1.0")

    MULTIPART_BOUNDARY = b"pyrobusta-boundary"

    CONTENT_LENGTH_ERROR = b"Content-Length mismatch"
    HEADER_ERROR = b"Invalid headers"
    MULTIPART_BOUNDARY_ERROR = b"Invalid multipart boundary"
    BAD_REQUEST_ERROR = b"Bad request"

    def __init__(self):
        # [State machine]
        self.state = self._parse_request_line_st
        self.status_code = None
        self.response_headers = []

        # [Recived request]
        self.version = None
        self.headers = {}
        self.method = None
        self.url = None
        self.content_length_cnt = 0

        # [Multipart state]
        self.mp_boundary = None

    # =========================================
    # Methods/decorators for routing
    # =========================================

    @classmethod
    def register(
        cls, endpoint: str, callback: object | str, method: str = "GET"
    ) -> None:
        """
        Register an endpoint with a callback function
        :param endpoint: name of the endpoint
        :param callback: callback function
        :param method: HTTP method name
        """
        endpoint = endpoint.encode(cls.ASCII)
        method = method.encode(cls.ASCII)
        endpoint_exists = cls._get_callback(endpoint, method) is not None

        if method not in cls.METHODS:
            raise ValueError(f"method must be one of {cls.METHODS}")
        if endpoint_exists:
            raise ValueError("endpoint exists")
        cls.ENDPOINTS.append((endpoint, callback, method))

    @staticmethod
    def route(endpoint, method):
        """
        Decorator for registering endpoint callback functions.
        """

        def decorator(func):
            HttpEngine.register(endpoint, func, method)
            return func

        return decorator

    # =========================================
    # Static helpers for parsing
    # =========================================

    @staticmethod
    def _lookup(tuple_, key):
        idx = tuple_.index(key)
        return tuple_[idx + 1]

    @classmethod
    def _get_callback(cls, endpoint, method):
        for e in cls.ENDPOINTS:
            if endpoint == e[0] and method == e[2]:
                return e[1]

    @classmethod
    def _has_endpoint(cls, endpoint):
        for e in cls.ENDPOINTS:
            if endpoint == e[0]:
                return True
        return False

    @classmethod
    def _supported_methods(cls, endpoint):
        supported_methods = []
        for method in cls.METHODS:
            if cls._get_callback(endpoint, method) is not None:
                supported_methods.append(method)
        return supported_methods

    @classmethod
    def _parse_headers(cls, raw_headers: memoryview) -> dict[str, str | int]:
        """
        Basic parser to extract HTTP/MIME headers
        :param raw_headers: headers
        """
        header_lines = bytes(raw_headers).split(b"\r\n")
        headers = {}
        for line in header_lines:
            # pylint: disable=W0511
            # TODO: support for UTF-8 in field values (e.g filenames), can be board dependent
            if any(c > 127 for c in line):
                raise HeaderParsingError("Non-ASCII character")
            if b":" not in line:
                raise HeaderParsingError()
            name, value = line.split(b":", 1)
            name = name.strip().lower().decode(cls.ASCII)
            if name == cls.CONTENT_LENGTH:
                value = int(value.strip())
            else:
                value = value.strip().decode(cls.ASCII)
            headers[name] = value
        return headers

    @staticmethod
    def _is_multipart(headers: dict) -> str:
        """Determine from the headers if a request is multipart, and return the boundary value"""
        content_type = headers.get("content-type")
        if content_type and content_type.lower().startswith("multipart/form-data"):
            parts = content_type.split(";")
            for part in parts[1:]:
                if "=" in part:
                    key, value = part.strip().split("=", 1)
                    if key.strip().lower() == "boundary":
                        boundary = value.strip().strip('"')
                        return boundary if boundary else None
        return None

    @classmethod
    def _parse_body_part(cls, part: memoryview) -> tuple[dict, bytes]:
        """Parse part headers and body and return them as a tuple"""
        blank_idx = -1
        for i in range(len(part) - 3):
            if part[i : i + 4] == b"\r\n\r\n":
                blank_idx = i
                break
        if blank_idx == -1:
            raise HeaderParsingError()
        headers = cls._parse_headers(part[:blank_idx])
        body = part[blank_idx + 4 :]
        return headers, body

    # =========================================
    # Helpers for state machine termination
    # =========================================

    def _set_response_header(self, key, value):
        if (
            key in self.response_headers
            and (index := self.response_headers.index(key) % 2) == 0
        ):
            self.response_headers[index + 1] = value
        else:
            self.response_headers.append(key)
            self.response_headers.append(value)

    def terminate(self, status_code: int, content_type: bytes = b"text/plain"):
        """
        Terminate state machine with status code and response content-type
        :param status_code: HTTP status code
        :param content_type: content-type of the response
        """
        self.state = None
        self.status_code = status_code
        if content_type:
            self._set_response_header(b"content-type", content_type)
        self._set_response_header(b"connection", b"close")

    def _write_response_head(self, tx, content_length: int = 0):
        """
        Write response status & header to the output,
        with optional content-length value
        """
        # Discard already accumulated content (e.g. 500 response on unexpected errors)
        tx.consume()
        tx.write(self.version)
        tx.write(b" ")
        tx.write(self._lookup(self.RESP_HEADERS, self.status_code))
        if content_length is not None:
            tx.write(b"\r\n")
            tx.write(b"content-length: %s" % str(content_length).encode(self.ASCII))
        for i in range(0, len(self.response_headers), 2):
            key = self.response_headers[i]
            value = self.response_headers[i + 1]
            tx.write(b"\r\n")
            tx.write(key)
            tx.write(b": ")
            tx.write(value)
        tx.write(b"\r\n\r\n")

    def _generate_response(self, tx, body: bytes | str | dict | tuple | list):
        """
        Write the complete response to the output, including status
        and headers. Return a BytesIO object if the content length
        exceeds the remaining buffer capacity, to delegate the writing
        of the response body to the transport layer.
        """
        if not body:
            self._write_response_head(tx, 0)
            body_encoded = b""
        elif isinstance(body, (bytes, bytearray, memoryview)):
            self._write_response_head(tx, len(body))
            body_encoded = body
        elif isinstance(body, str):
            body_encoded = body.encode()
            self._write_response_head(tx, len(body_encoded))
        elif isinstance(body, (dict, tuple, list)):
            body_encoded = dumps(body).encode()
            self._write_response_head(tx, len(body_encoded))
        else:
            self.on_failure(tx, b"Unhandled body type")
            return
        if self.method != self.HEAD:
            if len(body_encoded) > tx.capacity - tx.size():
                return BytesIO(body_encoded)
            tx.write(body_encoded)

    def on_client_error(self, tx, info: bytes):
        """Terminate state machine and write 400 response"""
        self.terminate(400)
        response = info
        self._write_response_head(tx, len(response))
        tx.write(response)

    def on_missing_resource(self, tx):
        """Terminate state machine and write 404 response"""
        self.terminate(404)
        self._write_response_head(tx)

    def on_method_not_allowed(self, tx):
        """Terminate state machine and write 405 response"""
        self.terminate(405)
        self._write_response_head(tx)

    def on_timeout(self, tx):
        """Terminate state machine and write 408 response"""
        self.terminate(408)
        self._write_response_head(tx)

    def on_buffer_full(self, tx):
        """Terminate state machine and write 413 response"""
        self.terminate(413)
        self._write_response_head(tx)

    def on_failure(self, tx, info: bytes):
        """Terminate state machine and write 500 response"""
        self.terminate(500)
        self._write_response_head(tx, len(info))
        tx.write(info)

    def on_busy(self, tx):
        """Terminate state machine and write 503 response"""
        self.terminate(503)
        self._write_response_head(tx)

    def on_unsupported_version(self, tx):
        """Terminate state machine and write 505 response"""
        self.terminate(505)
        self._write_response_head(tx)

    # ================================================================================
    # Parser states
    # - all states must handle rx and tx buffer arguments for reading and writing data
    # - mandatory methods/attributes of rx: find(), peek(), consume(), size()
    # - mandatory methods/attributes of tx: capacity, consume(), write(), size()
    # - rx/tx reference implementation: SlidingBuffer (pyrobusta.stream.buffer)
    # ================================================================================

    def _parse_request_line_st(self, rx, tx):
        """State for parsing the request line"""
        status_line_sep = rx.find(b"\r\n")
        if status_line_sep == -1:
            return
        status_parts = bytes(rx.peek(status_line_sep)).split()
        if len(status_parts) != 3:
            self.on_client_error(tx, self.BAD_REQUEST_ERROR)
            return
        self.method = status_parts[0]
        self.url = status_parts[1]
        self.version = status_parts[2]
        if self.method not in self.METHODS:
            self.on_method_not_allowed(tx)
            return
        if self.version not in self.SUPPORTED_VERSIONS:
            self.on_unsupported_version(tx)
            return
        rx.consume(status_line_sep + 2)
        self.state = self._parse_headers_st

    def _parse_headers_st(self, rx, tx):
        """State for parsing headers"""
        if (blank_idx := rx.find(b"\r\n\r\n")) == -1:
            return
        try:
            self.headers = self._parse_headers(rx.peek(blank_idx))
        except HeaderParsingError:
            self.on_client_error(tx, self.HEADER_ERROR)
            return
        rx.consume(blank_idx + 4)
        self.state = self._route_request_st

    def _has_payload(self):
        return (
            self.CONTENT_LENGTH in self.headers
            and self.headers[self.CONTENT_LENGTH] > 0
        )

    def _route_request_st(self, _, tx):
        """
        State for routing requests
        - supported ways: static resources, endpoint callback functions
        """
        if self._has_endpoint(self.url) and (
            self._get_callback(self.url, self.method) is not None
            or self.method == self.OPTIONS
            or (
                self.method == self.HEAD
                and self._get_callback(self.url, self.GET) is not None
            )
        ):
            if self.method == self.OPTIONS:
                supported_methods = self._supported_methods(self.url)
                self._set_response_header(b"allow", b", ".join(supported_methods))
                self.terminate(204, None)
                self._write_response_head(tx, None)
                return
            if self._has_payload():
                if self.method == self.HEAD:
                    self.on_client_error(tx, self.BAD_REQUEST_ERROR)
                    return
                if mp_boundary := self._is_multipart(self.headers):
                    self.mp_boundary = mp_boundary.encode(self.ASCII)
                    self.state = self._start_multipart_parser_st
                else:
                    self.state = self._recv_payload
            else:
                self.state = self._app_endpoint_st
            return

        if (
            self._has_endpoint(self.url)
            and self._get_callback(self.method, self.url) is None
        ):
            supported_methods = self._supported_methods(self.url)
            self._set_response_header(b"allow", b", ".join(supported_methods))
            self.on_method_not_allowed(tx)
            return
        if self.method == self.GET:
            resource = b"index.html" if not self.url else self.url
            self.state = lambda _rx, _tx: self._send_file_st(_rx, _tx, resource)
            return
        self.on_missing_resource(tx)

    def _recv_payload(self, rx, tx):
        if self.headers[self.CONTENT_LENGTH] > rx.size():
            return
        if self.headers[self.CONTENT_LENGTH] < rx.size():
            self.on_client_error(tx, self.CONTENT_LENGTH_ERROR)
            return
        self.state = self._app_endpoint_st

    def _app_endpoint_st(self, rx, tx):
        """Process a request by registered callback functions"""
        method = self.GET if self.method == self.HEAD else self.method
        callback = self._get_callback(self.url, method)
        if self._has_payload():
            self.state = None
            dtype, data = callback(self, bytes(rx.peek()))
            dtype = dtype.encode(self.ASCII)
        else:
            if not callable(callback):
                # Handle as a static resource
                self.state = lambda _rx, _tx: self._send_file_st(
                    _rx, _tx, callback.encode(HttpEngine.ASCII)
                )
                return
            dtype, data = callback(self, b"")
            dtype = dtype.encode(self.ASCII)
        self._set_response_header(b"content-type", dtype)
        if dtype == b"image/jpeg":
            self.terminate(200, dtype)
            return self._generate_response(tx, data)
        if dtype in (b"multipart/x-mixed-replace", b"multipart/form-data"):
            part_content_type = data[0]
            callback = data[1]
            if type(callback).__name__ not in ("function", "closure"):
                self.on_failure(tx, b"Invalid response handler")
                return
            self.terminate(200, dtype)
            boundary = self.MULTIPART_BOUNDARY
            self._set_response_header(
                b"content-type", dtype + b"; boundary=" + boundary
            )
            self._write_response_head(tx, None)
            if self.method != self.HEAD:
                return self._multipart_wrapper_factory(
                    callback, part_content_type.encode(self.ASCII), boundary
                )
            return
        self.terminate(200, dtype)
        return self._generate_response(tx, data)

    def _send_file_st(self, _, tx, web_resource: bytes):
        """State for returning a static resource"""
        # Normalize path
        parts = []
        for p in web_resource.split(b"/"):
            if p in (b".", b""):
                continue
            if p == b"..":
                if parts:
                    parts.pop()
            else:
                parts.append(p)
        if parts[0].decode(self.ASCII) not in get_config("http_served_paths").split():
            self.on_missing_resource(tx)
            return
        extension = web_resource.rsplit(b".", 1)[-1]
        norm_path = b"/".join(parts)

        try:
            content_type = self._lookup(self.CONTENT_TYPES, extension)
        except ValueError:
            content_type = self._lookup(self.CONTENT_TYPES, b"raw")
        try:
            self._set_response_header(
                b"content-length", str(stat(norm_path)[6]).encode(HttpEngine.ASCII)
            )
            self.terminate(200, content_type)
            self._write_response_head(tx, None)
            if self.method != self.HEAD:
                return open(norm_path, "rb")
            return
        except OSError:
            self.on_missing_resource(tx)

    def _start_multipart_parser_st(self, rx, tx):  # pylint: disable=W0613
        self.on_failure(tx, b"Multipart handling is disabled")

    @staticmethod
    def _multipart_wrapper_factory(callback, content_type: bytes, boundary: bytes):
        pass


def enable_optional_features():
    """
    Enable related optional features, set in the config.
    """
    if get_config("http_multipart").lower() == "true":
        from pyrobusta.protocol import http_multipart

        http_multipart.apply_patches()
