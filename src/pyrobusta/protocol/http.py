"""
This module is responsible HTTP protocol parsing with partial guarantees on RFC compliance.
"""

from json import dumps
from io import BytesIO
from os import stat

from pyrobusta import WORKING_DIR
from pyrobusta.stream.buffer import BufferOverflowError
from pyrobusta.utils.lexpath import is_child_path_of, normalize_path, iterate_segments
from pyrobusta.protocol import (
    InvalidHeaders,
    MalformedRequest,
    InvalidContentLength,
)


class HttpEngine:
    """
    HTTP protocol parser state machine and middleware.
    - each instance represents a connection, allowing a request to be parsed through a state machine
    - provides an adapter/routing layer for applications (see also: register(), route())

    Feature flags (configured in pyrobusta.env)
    - http_files_api: serve files at the /files API, with support for CRUD methods
    - http_multipart: support for multipart requests/responses
    - http_auth: authenticate and authorize users
    - http_browser_security: enable security features like CSRF protection and hardening headers
    """

    __slots__ = (
        "id",
        "state",
        "status_code",
        "resp_headers",
        "resp_handler",
        "version",
        "headers",
        "method",
        "url",
        "query",
        "content_len_cnt",
        "recv_chunk_size",
        "is_req_empty",
        "_is_req_complete",
        "_extras",
    )

    ROUTES = []  # (route, handler, HTTP method)
    RESP_HEADERS = (
        200,
        b"200 OK",
        201,
        b"201 Created",
        204,
        b"204 No Content",
        400,
        b"400 Bad Request",
        401,
        b"401 Unauthorized",
        403,
        b"403 Forbidden",
        404,
        b"404 Not Found",
        405,
        b"405 Method Not Allowed",
        408,
        b"408 Request Timeout",
        413,
        b"413 Content Too Large",
        415,
        b"415 Unsupported Media Type",
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
        b"csv",
        b"text/csv",
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
        b"svg",
        b"image/svg",
        b"gif",
        b"image/gif",
        b"webp",
        b"image/webp",
        b"txt",
        b"text/plain",
        b"log",
        b"text/plain",
    )

    SAFE_CONTENT_TYPES = (
        b"application/json",
        b"image/gif",
        b"image/jpeg",
        b"image/png",
        b"image/webp",
        b"image/x-icon",
        b"text/csv",
        b"text/plain",
    )

    DELETE = b"DELETE"
    GET = b"GET"
    HEAD = b"HEAD"
    OPTIONS = b"OPTIONS"
    PATCH = b"PATCH"
    POST = b"POST"
    PUT = b"PUT"
    METHODS = (DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT)
    SUPPORTED_VERSIONS = (b"HTTP/1.1", b"HTTP/1.0")
    SESSION_COUNTER = 0

    SERVED_PATHS = None
    PROTECTED_PATHS = None
    USER_DIRECTORY = None
    TLS = False
    POST_HOOKS = []

    @classmethod
    def new_statemachine_id(cls):
        """
        Create a new unique ID for the HTTP statemachine.
        """
        cls.SESSION_COUNTER = (cls.SESSION_COUNTER + 1) & 0xFFFFFFFF
        return cls.SESSION_COUNTER

    def __init__(self):
        # [State machine]
        self.id = self.new_statemachine_id()
        self.state = self._start_parser
        self.status_code = None
        self.resp_headers = []
        self.resp_handler = None

        # [Recived request]
        self.version = None
        self.headers = {}
        self.method = None
        self.url = None
        self.query = None
        self.content_len_cnt = 0
        self.recv_chunk_size = 0
        self.is_req_empty = True
        self._is_req_complete = False

        # [Extras]
        self._extras = None

    def reset(self):
        """
        Reset internal state to reuse a state machine object.
        """
        self.id = self.new_statemachine_id()
        self.state = self._start_parser
        self.status_code = None
        self.resp_headers.clear()
        self.resp_handler = None
        self.version = None
        self.headers.clear()
        self.method = None
        self.url = None
        self.query = None
        self.content_len_cnt = 0
        self.recv_chunk_size = 0
        self.is_req_empty = True
        self._is_req_complete = False
        self._extras = None

    # =========================================
    # Methods/decorators for routing
    # =========================================

    @classmethod
    def register(cls, route: str, handler: callable, method: str = "GET") -> None:
        """
        Register a route handler.
        :param route: URL path to be routed e.g. "/app/resource"
        :param handler: function callback
        :param method: HTTP method name
        """
        route = route.encode("ascii")
        method = method.encode("ascii")
        route_exists = cls._get_handler(route, method) is not None

        if method not in cls.METHODS:
            raise ValueError(f"method must be one of {cls.METHODS}")
        if route_exists:
            raise ValueError("route exists")
        cls.ROUTES.append((route, handler, method))

    @classmethod
    def deregister(cls, route: str, method: str) -> None:
        """
        Deregister a route handler.
        :param route: URL path to be routed e.g. "/app/resource"
        :param method: HTTP method name
        """
        route = route.encode("ascii")
        method = method.encode("ascii")

        if handler := cls._get_handler(route, method):
            cls.ROUTES.remove((route, handler, method))

    @staticmethod
    def route(route: str, method: str):
        """
        Decorator for registering route handlers.
        :param route: URL path to be routed e.g. "/app/resource"
        :param method: HTTP method name
        """

        def decorator(func):
            HttpEngine.register(route, func, method)
            return func

        return decorator

    # =========================================
    # Helpers for parsing
    # =========================================

    @staticmethod
    def percent_decode(s: str):
        """
        Decode percent-encoded input.
        """
        out = []
        i = 0
        while i < len(s):
            if (
                s[i] == "%"
                and i + 2 < len(s)
                and all(c in "0123456789abcdefABCDEF" for c in s[i + 1 : i + 3])
            ):
                out.append(chr(int(s[i + 1 : i + 3], 16)))
                i += 3
            else:
                out.append(s[i])
                i += 1
        return "".join(out)

    def path_segment(self, idx: int):
        """
        Return the nth path segment of the URL path. The index is shifted by one to
        ignore the first empty segment before the leading slash ('/').
        """
        return self.url.split(b"/")[idx + 1].decode("ascii")

    def get_query_param(self, key: str, default: str = None) -> str:
        """
        Parse a query and return the value belonging to a key
        according to the x-www-form-urlencoded format.
        :param key: key to parse from the query
        :param default: default value to return when key is not present
        :return: value of the key or default
        """
        if not self.query or not key:
            return default

        if self.query.startswith(key + "="):
            idx_start = 0
        elif (idx_start := self.query.find("&" + key + "=")) != -1:
            idx_start += 1
        elif default is None:
            raise KeyError()
        else:
            return default

        idx_end = -1
        idx_end = self.query.find("&", idx_start)
        if idx_end > -1:
            return self.query[idx_start + len(key) + 1 : idx_end]
        return self.query[idx_start + len(key) + 1 :]

    def get_cookie(self, name, default=None):
        """
        Obtain a named cookie from the request headers.
        """
        cookie_header = self.headers.get("cookie", "")
        name = name.lower()
        for part in iterate_segments(cookie_header, ";"):
            cookie_sep = part.find("=")
            if cookie_sep == -1:
                continue
            key = part[:cookie_sep].strip()
            if key.lower() == name:
                return part[cookie_sep + 1 :].strip()
        return default

    @staticmethod
    def _is_matching_url_path(path: bytes, pattern: bytes) -> bool:
        """
        Match a URL path against a pattern that can contain wildcard segments e.g.
        /path/{wildcard}/resource where {wildcard} matches any non-empty string in
        that segment. /path/to/{wildcard:path} matches multiple path segments, only
        allowed for trailing segments. (e.g. "/{wildcard:path}/resource" is forbidden)
        """
        if path == pattern:
            return True
        i = j = 0
        n, m = len(path), len(pattern)
        while i < n and j < m:
            # Find next segment boundaries
            ni = path.find(b"/", i)
            nj = pattern.find(b"/", j)
            if ni == -1:
                ni = n
            if nj == -1:
                nj = m
            path_seg = path[i:ni]
            pat_seg = pattern[j:nj]
            if path_seg != pat_seg:
                if not (
                    len(pat_seg) >= 2
                    and pat_seg[0] == 123  # {
                    and pat_seg[-1] == 125  # }
                    and len(path_seg) > 0
                ):
                    return False
                if pat_seg.endswith(b":path}"):
                    return True
            i = ni + 1
            j = nj + 1
        return i >= n and j >= m

    @staticmethod
    def _lookup(tuple_, key):
        idx = tuple_.index(key)
        return tuple_[idx + 1]

    @classmethod
    def _get_handler(cls, route, method: bytes):
        for e in cls.ROUTES:
            if cls._is_matching_url_path(route, e[0]) and method == e[2]:
                return e[1]

    @classmethod
    def _has_route(cls, route: bytes):
        for e in cls.ROUTES:
            if cls._is_matching_url_path(route, e[0]):
                return True
        return False

    @classmethod
    def _supported_methods(cls, route: bytes):
        supported_methods = []
        for method in cls.METHODS:
            if cls._get_handler(route, method) is not None:
                supported_methods.append(method)
        return supported_methods

    @classmethod
    def _parse_headers(cls, raw_headers: memoryview) -> dict[str, str | int]:
        """
        Basic parser to extract HTTP/MIME headers.
        """
        headers = {}
        start = 0
        n = len(raw_headers)

        while start < n:
            end = start
            colon = -1
            while end < n:
                c = raw_headers[end]
                if c > 127:
                    raise InvalidHeaders()
                if c == 58 and colon == -1:
                    colon = end
                if end + 1 < n and c == 13 and raw_headers[end + 1] == 10:
                    break
                end += 1

            if colon in (-1, start):
                raise InvalidHeaders()

            for i in range(start, colon):
                c = raw_headers[i]
                if not (
                    48 <= c <= 57  # 0-9
                    or 65 <= c <= 90  # A-Z
                    or 97 <= c <= 122  # a-z
                    or c in (45, 95)  # -_
                ):
                    raise InvalidHeaders()

            name = bytes(raw_headers[start:colon]).strip(b" ").lower().decode("ascii")
            value_bytes = bytes(raw_headers[colon + 1 : end]).strip(b" ")

            if any((c < 32 and c != 9) or c == 127 for c in value_bytes):
                raise InvalidHeaders()
            if name == "content-length":
                if not all(48 <= c <= 57 for c in value_bytes):
                    raise InvalidHeaders()
                value = int(value_bytes)
            else:
                value = value_bytes.decode("ascii")
            if name not in headers and value:
                headers[name] = value
            elif value:
                headers[name] += ", " + value  # Combined field value

            start = end + 2
        return headers

    # =========================================
    # Helpers for state machine termination
    # =========================================

    def set_response_header(self, key: bytes, value: bytes, override: bool = True):
        """
        Set a response header by key and value.
        :param key: HTTP header key
        :param value: HTTP header value
        :param override: override existing header
        """
        key = key.lower()
        if (
            key in self.resp_headers
            and (index := self.resp_headers.index(key)) % 2 == 0
            and override
        ):
            self.resp_headers[index + 1] = value
        else:
            self.resp_headers.append(key)
            self.resp_headers.append(value)

    def get_response_header(self, key: bytes):
        """
        Get a response header by key.
        :param key: HTTP header key
        """
        if (
            key in self.resp_headers
            and (index := self.resp_headers.index(key)) % 2 == 0
        ):
            return self.resp_headers[index + 1]

    def write_response_head(self, tx):
        """
        Write response status and header to an output buffer.
        :param tx: response buffer
        """
        tx.consume()  # Discard already accumulated content, required on abrupt errors
        tx.write(self.version)
        tx.write(b" ")
        tx.write(self._lookup(self.RESP_HEADERS, self.status_code))
        for i in range(0, len(self.resp_headers), 2):
            key = self.resp_headers[i]
            value = self.resp_headers[i + 1]
            tx.write(b"\r\n")
            tx.write(key)
            tx.write(b": ")
            tx.write(value)
        tx.write(b"\r\n\r\n")

    def set_response_body(
        self,
        body: bytes | str | dict | tuple | list,
        content_type: str = "text/plain",
    ):
        """
        Serialize and wrap the response body with a BytesIO object, stored by the
        resp_handler member. resp_handler can be used for writing the body by the
        transport layer. This method also updates the content-type and content-length
        headers. In the case of a HEAD request, the body is omitted.
        :param body: body to be sent in the response
        :param content_type: content-type of the body
        """
        if not body:
            body_encoded = b""
        if isinstance(body, (bytes, bytearray, memoryview)):
            body_encoded = body
        elif isinstance(body, str):
            body_encoded = body.encode()
        elif isinstance(body, (dict, tuple, list)):
            body_encoded = dumps(body).encode()
        else:
            raise ValueError("Unhandled body type")

        self.set_response_header(
            b"content-length", str(len(body_encoded)).encode("ascii")
        )

        # Unset and clean up existing handler if set
        if type(self.resp_handler).__name__ in ("FileIO", "BytesIO"):
            self.resp_handler.close()
            self.resp_handler = None

        if len(body_encoded):
            self.set_response_header(b"content-type", content_type.encode("ascii"))

            if self.method != self.HEAD:
                self.resp_handler = BytesIO(body_encoded)

    def do_keep_alive(self):
        """
        Determine if the connection should be kept alive
        depending on the HTTP version and headers sent in the request.
        """
        if self.is_terminated() and not self._is_req_complete:
            return False

        connection_tokens = [
            token.strip().lower()
            for token in self.headers.get("connection", "").split(",")
        ]
        return (self.version == b"HTTP/1.0" and "keep-alive" in connection_tokens) or (
            self.version == b"HTTP/1.1" and "close" not in connection_tokens
        )

    def _handle_route_response(self, handler_response: tuple | None):
        """
        Terminate the state machine based on the return value of a user-defined route handler.
        If the handler does not explicitly set a status code, default to HTTP 200. If the handler
        returns a response body and content type, set them accordingly.
        """
        self.terminate(self.status_code or 200)

        if handler_response is None:
            return

        dtype, data = handler_response
        if dtype.startswith("multipart/") and callable(data):
            self.set_response_header(b"transfer-encoding", b"chunked")
            self.generate_multipart_response(data, dtype)
            return

        self.set_response_body(data, content_type=dtype)

    def terminate(self, status_code: int):
        """
        Regular state machine termination with a specific status code.
        """
        self.state = self._terminal_st
        if not isinstance(status_code, int) or status_code not in self.RESP_HEADERS:
            raise ValueError("Invalid status")
        self.status_code = status_code

    def abort(self, status_code: int):
        """
        Abort state machine due to runtime errors.
        Reset any header or response body set earlier.
        """
        self.resp_headers = []
        self.set_response_body(b"")
        self.terminate(status_code)

    def is_request_empty(self):
        """
        Returns false if the state machine has received any input.
        """
        return self.is_req_empty

    def is_terminated(self):
        """
        Returns true if the state machine is terminated.
        """
        return self.state is None

    def run(self, rx):
        """
        Run the state machine, consuming the content of a request buffer (rx).
        Unlike individual states, this method does not raise an exception.
        This method returns on every state transition.
        """
        if self.is_terminated():
            return
        try:
            self.state(rx)
        except BufferOverflowError:
            self.abort(500)
            self.set_response_body(b"Buffer full")
        except InvalidHeaders:
            self.abort(400)
            self.set_response_body(b"Invalid headers")
        except InvalidContentLength:
            self.abort(400)
            self.set_response_body(b"Content length mismatch")
        except MalformedRequest:
            self.abort(400)
            self.set_response_body(b"Malformed request")
        except Exception as e:  # pylint: disable=W0718
            from pyrobusta.utils import logging

            logging.warning("%s.run: error=[%s]", __name__, e)
            self.abort(500)
            self.set_response_body(b"Internal Server Error")

    # ========================================
    # Helpers for routing, state machine logic
    # ========================================

    def is_chunked(self):
        """
        Determines if the request has a payload with chunked transfer-encoding.
        """
        return self.headers.get("transfer-encoding", "").lower() == "chunked"

    def is_multipart(self):
        """
        Determines if the request has a multipart payload.
        """
        return self.headers.get("content-type", "").lower().startswith("multipart/")

    def has_payload(self):
        """
        Determines if the request has a body.
        """
        return (
            "content-length" in self.headers and self.headers["content-length"] > 0
        ) or self.is_chunked()

    def _consume_payload(self, rx, size, last=False):
        """
        Consume data from the request buffer and increment content length counter.
        Raise an exception if the content length is exceeded. Allow strict checking
        of content length when the last flag is set. When the request is chunked,
        the content length should not be set, otherwise it is ignored.
        """
        assert not self._is_req_complete
        if (
            not self.is_chunked()
            and "content-length" in self.headers
            and (
                (self.content_len_cnt + size > self.headers["content-length"])
                or (
                    last
                    and self.headers["content-length"] != self.content_len_cnt + size
                )
            )
        ):
            raise InvalidContentLength()
        self.content_len_cnt += size
        rx.consume(size)
        self._is_req_complete = last

    # ================================================================================
    # Parser states
    # - all states must handle rx buffer argument for reading request data
    # - mandatory methods/attributes of rx: find(), peek(), consume(), size()
    # - reference implementation: SlidingBuffer (pyrobusta.stream.buffer)
    # ================================================================================

    def _start_parser(self, rx):
        """
        Initial state.
        """
        if rx.size():
            self.is_req_empty = False
            self.state = self._parse_request_line_st

    def _parse_request_line_st(self, rx):
        """
        Parse the request line.
        """
        status_line_sep = rx.find(b"\r\n")
        if status_line_sep == -1:
            return
        status_parts = bytes(rx.peek(status_line_sep)).split()
        if len(status_parts) != 3:
            raise MalformedRequest()
        self.method = status_parts[0]
        url_parts = status_parts[1].split(b"?", 1)
        self.url = url_parts[0]
        self.query = (
            ""
            if len(url_parts) == 1
            else self.percent_decode(url_parts[1].decode("ascii"))
        )
        self.version = status_parts[2]
        if self.method not in self.METHODS:
            self.terminate(405)
            return
        if self.version not in self.SUPPORTED_VERSIONS:
            self.terminate(505)
            return
        rx.consume(status_line_sep + 2)
        self.state = self._parse_headers_st

    def _parse_headers_st(self, rx):
        """
        Parse HTTP headers.
        """
        if (blank_idx := rx.find(b"\r\n\r\n")) == -1:
            return
        self.headers = self._parse_headers(rx.peek(blank_idx))
        if self.version == b"HTTP/1.1" and "host" not in self.headers:
            raise InvalidHeaders()
        rx.consume(blank_idx + 4)
        if hasattr(self, "_handle_auth_st"):
            # Authenticate & authorize if enabled
            self.state = getattr(self, "_handle_auth_st")
        else:
            self.state = self._route_request_st

    def _route_request_st(self, _):
        """
        Route requests based on registered route handlers.
        If no route is registered, fall back to file serving.
        """
        if self._has_route(self.url) and (
            self._get_handler(self.url, self.method) is not None
            or self.method == self.OPTIONS
            or (
                self.method == self.HEAD
                and self._get_handler(self.url, self.GET) is not None
            )
        ):
            if self.method == self.OPTIONS:
                supported_methods = self._supported_methods(self.url)
                self.set_response_header(b"allow", b", ".join(supported_methods))
                self.terminate(204)
                return
            if self.has_payload():
                if self.method in (self.GET, self.HEAD):
                    raise MalformedRequest()
                if self.is_multipart():
                    if hasattr(self, "_start_multipart_parser_st"):
                        self.state = getattr(self, "_start_multipart_parser_st")
                    else:
                        self.abort(503)
                        return
                elif self.is_chunked():
                    if "content-length" in self.headers:
                        # Ignore content-length as per RFC 9112,
                        # chunked transfer-encoding takes precedence
                        pass
                    self.state = self._recv_chunk_size_st
                else:
                    self.state = self._recv_payload_st
            else:
                self.state = self._handle_route_st
            return

        # Request does not have a registered route
        if (
            self._has_route(self.url)
            and self._get_handler(self.url, self.method) is None
        ):
            supported_methods = self._supported_methods(self.url)
            self.set_response_header(b"allow", b", ".join(supported_methods))
            self.terminate(405)
            return
        # Fallback: serve file
        if self.method in (self.GET, self.HEAD):
            if self.has_payload():
                raise MalformedRequest()
            self._is_req_complete = True
            self.state = self._fs_retrieve_st
            return
        self.terminate(404)

    def _recv_chunk_size_st(self, rx):
        """
        State for determining the chunk size (transfer-encoding: chunked).
        """
        if (blank_idx := rx.find(b"\r\n")) == -1:
            return
        self.recv_chunk_size = int(bytes(rx.peek(blank_idx)), 16)
        if self.recv_chunk_size < 0:
            raise InvalidContentLength()
        self._consume_payload(rx, blank_idx + 2)
        self.state = self._recv_chunk_st

    def _recv_chunk_st(self, rx):
        """
        State for receiving a complete chunk (transfer-encoding: chunked).
        """
        if self.recv_chunk_size + 2 > rx.size():
            return
        if self.recv_chunk_size + 2 <= rx.size():
            if rx.peek(self.recv_chunk_size + 2)[-2:] != b"\r\n":
                raise InvalidContentLength()
            self.state = self._handle_route_st

    def _recv_payload_st(self, rx):
        """
        State for receiving the request body.
        """
        if self.headers["content-length"] > rx.size():
            return
        self.state = self._handle_route_st

    def _handle_route_st(self, rx):
        """
        Process a request by a registered route handler.
        HEAD requests are temporarily mapped to GET for routing and handler execution.
        """
        method = self.GET if self.method == self.HEAD else self.method
        handler = self._get_handler(self.url, method)
        if self.has_payload():
            if self.is_chunked():
                if self.recv_chunk_size:
                    handler_response = handler(
                        self, bytes(rx.peek(self.recv_chunk_size))
                    )
                    self._consume_payload(rx, self.recv_chunk_size + 2)
                    if not self.state == self._terminal_st:  # pylint: disable=W0143
                        self.state = self._recv_chunk_size_st
                        return
                else:
                    # Last chunk, pass empty body to signal end of request body
                    handler_response = handler(self, b"")
                    self._consume_payload(rx, self.recv_chunk_size + 2, last=True)
            else:
                handler_response = handler(
                    self, bytes(rx.peek(self.headers["content-length"]))
                )
                self._consume_payload(rx, self.headers["content-length"], last=True)
        else:
            handler_response = handler(self, b"")
            self._is_req_complete = True

        self._handle_route_response(handler_response)

    def is_path_served(self, norm_path: str):
        """
        Returns true if a normalized path is configured to be served.
        """
        return (
            is_child_path_of(norm_path, self.SERVED_PATHS)  # pylint: disable=E1101
            and not norm_path in self.PROTECTED_PATHS  # pylint: disable=E1101
        )

    def _fs_retrieve_st(self, _):
        """
        State for retrieving a file under /www.
        /www is prepended to the path by default.
        """
        if self.url == b"/":
            target_path = "/www/index.html"
        else:
            target_path = "/www" + self.url.decode("ascii")
        norm_path = normalize_path(target_path)

        try:
            if not self.is_path_served(norm_path):
                stat(norm_path)
                self.terminate(403)
                return

            try:
                extension = target_path.rsplit(".", 1)[-1].lower().encode("ascii")
                content_type = self._lookup(self.CONTENT_TYPES, extension)
            except ValueError:
                content_type = b"application/octet-stream"

            if (
                is_child_path_of(target_path, (self.USER_DIRECTORY,))
                and content_type not in self.SAFE_CONTENT_TYPES
            ):
                self.set_response_header(b"content-disposition", b"attachment")

            self.set_response_header(
                b"content-length", str(stat(norm_path)[6]).encode("ascii")
            )
            self.set_response_header(b"content-type", content_type)
            self.terminate(200)
            if self.method != self.HEAD:
                self.resp_handler = open(norm_path, "rb")  # pylint: disable=R1732
            return
        except OSError:
            self.terminate(404)

    def generate_multipart_response(self, callback, dtype):  # pylint: disable=W0613
        """
        Generate multipart response depening on the exact content type (placeholder).
        """
        self.abort(503)

    def _apply_keepalive_headers(self):
        """
        Apply headers for persistent connection management.
        """
        if (
            self.version == b"HTTP/1.0"
            and self.do_keep_alive()
            and self._is_req_complete
        ):
            self.set_response_header(b"connection", b"keep-alive")
        elif self.version == b"HTTP/1.1" and (
            not self.do_keep_alive() or not self._is_req_complete
        ):
            self.set_response_header(b"connection", b"close")

    def _terminal_st(self, rx):  # pylint: disable=W0613
        """
        Terminal state for finalizing request/response processing.
        """
        self._apply_keepalive_headers()

        if not self.get_response_header(b"cache-control"):
            self.set_response_header(b"cache-control", b"no-store")

        if (
            self.get_response_header(b"transfer-encoding") != b"chunked"
            and self.get_response_header(b"content-length") is None
        ):
            self.set_response_header(b"content-length", b"0")

        for clb in self.POST_HOOKS:
            clb(self)

        self.state = None


def apply_patches(config, *_):
    """
    Apply patches to class attributes.
    """
    setattr(HttpEngine, "TLS", config.tls)
    setattr(HttpEngine, "USER_DIRECTORY", WORKING_DIR + "/www/user_data")
    setattr(HttpEngine, "SERVED_PATHS", config.http_served_paths)
    setattr(
        HttpEngine,
        "PROTECTED_PATHS",
        (
            config.path,
            config.passwd_file,
            config.roles_file,
            config.tls_cert_file,
            config.tls_key_file,
        ),
    )
