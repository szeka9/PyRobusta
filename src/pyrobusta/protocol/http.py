"""
This module is responsible HTTP protocol parsing
with partial guarantees on RFC compliance.
"""

from json import dumps
from io import BytesIO
from os import stat

from ..utils.config import (
    get_config,
    CONF_HTTP_MULTIPART,
    CONF_HTTP_FILES_API,
    CONF_HTTP_SERVED_PATHS,
)
from ..utils import logging, helpers
from ..stream.buffer import BufferFullError


class InvalidHeaders(ValueError):
    """Exception for errors occurring while parsing HTTP/MIME headers."""

    pass


class InvalidContentLength(ValueError):
    """Exception for content-length related erros."""

    pass


class MalformedRequest(ValueError):
    """Exception for malformed requests."""

    pass


class HttpEngine:
    """
    HTTP protocol parser state machine and middleware.
    - each instance represents a connection, allowing a request to be parsed
      through a state machine
    - provides an adapter/routing layer for applications
      through registered endpoints (see also: register(), route())
    - supports percent encoded URLs and query parameters (x-www-form-urlencoded)
    - allows applications to set response attributes (headers, status code)

    Feature flags (configured in pyrobusta.env)
    - http_files_api: serve files at the /files endpoint, with support for uploads,
      removal and directory listing
    - http_multipart: support for multipart requests/responses
    """

    __slots__ = (
        "id",
        "state",
        "status_code",
        "resp_headers",
        "resp_handler",
        "aborted",
        "version",
        "headers",
        "method",
        "url",
        "query",
        "content_len_cnt",
        "recv_chunk_size",
        "is_req_empty",
        "mp_boundary",
        "mp_is_first",
        "mp_is_last",
        "mp_delimiter",
        "mp_last_delimiter",
    )

    ENDPOINTS = []  # (endpoint, callback, method)
    RESP_HEADERS = (
        200,
        b"200 OK",
        201,
        b"201 Created",
        204,
        b"204 No Content",
        400,
        b"400 Bad Request",
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

    DELETE = b"DELETE"
    GET = b"GET"
    HEAD = b"HEAD"
    OPTIONS = b"OPTIONS"
    POST = b"POST"
    PUT = b"PUT"
    METHODS = (DELETE, GET, HEAD, OPTIONS, POST, PUT)
    SUPPORTED_VERSIONS = (b"HTTP/1.1", b"HTTP/1.0")
    SESSION_COUNTER = 0

    @classmethod
    def new_session_id(cls):
        """
        Create a new unique ID for the HTTP session.
        """
        cls.SESSION_COUNTER = (cls.SESSION_COUNTER + 1) & 0xFFFFFFFF
        return cls.SESSION_COUNTER

    def __init__(self):
        # [State machine]
        self.id = self.new_session_id()
        self.state = self._start_parser
        self.status_code = None
        self.resp_headers = []
        self.resp_handler = None
        self.aborted = False

        # [Recived request]
        self.version = None
        self.headers = {}
        self.method = None
        self.url = None
        self.query = None
        self.content_len_cnt = 0
        self.recv_chunk_size = 0
        self.is_req_empty = True

        # [Multipart state]
        self.mp_boundary = None

    def reset(self):
        """
        Reset internal state to reuse a state machine object.
        """
        self.id = self.new_session_id()
        self.state = self._start_parser
        self.status_code = None
        self.resp_headers.clear()
        self.resp_handler = None
        self.aborted = False
        self.version = None
        self.headers.clear()
        self.method = None
        self.url = None
        self.query = None
        self.content_len_cnt = 0
        self.recv_chunk_size = 0
        self.is_req_empty = True
        self.mp_boundary = None

    # =========================================
    # Methods/decorators for routing
    # =========================================

    @classmethod
    def register(cls, endpoint: str, callback: callable, method: str = "GET") -> None:
        """
        Register an endpoint with a callback function.
        :param endpoint: URL path to be routed e.g. "/app/resource"
        :param callback: callback function
        :param method: HTTP method name
        """
        endpoint = endpoint.encode("ascii")
        method = method.encode("ascii")
        endpoint_exists = cls._get_callback(endpoint, method) is not None

        if method not in cls.METHODS:
            raise ValueError(f"method must be one of {cls.METHODS}")
        if endpoint_exists:
            raise ValueError("endpoint exists")
        cls.ENDPOINTS.append((endpoint, callback, method))

    @classmethod
    def deregister(cls, endpoint: str, method: str) -> None:
        """
        Deregister an endpoint.
        :param endpoint: URL path to be routed e.g. "/app/resource"
        :param method: HTTP method name
        """
        endpoint = endpoint.encode("ascii")
        method = method.encode("ascii")

        if callback := cls._get_callback(endpoint, method):
            cls.ENDPOINTS.remove((endpoint, callback, method))

    @staticmethod
    def route(endpoint: str, method: str):
        """
        Decorator for registering endpoint callback functions.
        :param endpoint: URL path to be routed e.g. "/app/resource"
        :param method: HTTP method name
        """

        def decorator(func):
            HttpEngine.register(endpoint, func, method)
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
            if s[i] == "%" and i + 2 < len(s):
                out.append(chr(int(s[i + 1 : i + 3], 16)))
                i += 3
            else:
                out.append(s[i])
                i += 1
        return "".join(out)

    def path_segment(self, idx: int):
        """
        Return the nth path segment of the URL path.
        The index is shifted by one to ignore the first
        empty segment before the leading slash ('/').
        :param idx: index of the segment
        :return: string path segment
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

    @staticmethod
    def _is_matching_url_path(path: bytes, pattern: bytes) -> bool:
        """
        Match a URL path against a pattern that can contain wildcard segments
        e.g. /path/{wildcard}/resource where {wildcard} matches any non-empty
        string in that segment. /path/to/{wildcard:path} matches multiple path
        segments, only allowed for trailing segments.
        (e.g. "/{wildcard:path}/resource" is forbidden)
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
    def _get_callback(cls, endpoint, method: bytes):
        for e in cls.ENDPOINTS:
            if cls._is_matching_url_path(endpoint, e[0]) and method == e[2]:
                return e[1]

    @classmethod
    def _has_endpoint(cls, endpoint: bytes):
        for e in cls.ENDPOINTS:
            if cls._is_matching_url_path(endpoint, e[0]):
                return True
        return False

    @classmethod
    def _supported_methods(cls, endpoint: bytes):
        supported_methods = []
        for method in cls.METHODS:
            if cls._get_callback(endpoint, method) is not None:
                supported_methods.append(method)
        return supported_methods

    @classmethod
    def _parse_headers(cls, raw_headers: memoryview) -> dict[str, str | int]:
        """
        Basic parser to extract HTTP/MIME headers.
        """
        header_lines = bytes(raw_headers).split(b"\r\n")
        headers = {}
        for line in header_lines:
            # pylint: disable=W0511
            if any(c > 127 for c in line):
                raise InvalidHeaders("Non-ASCII character")
            if b":" not in line:
                raise InvalidHeaders()
            name, value = line.split(b":", 1)
            if not name:
                raise InvalidHeaders("Empty header name")
            for c in name:
                if (
                    48 <= c <= 57  # 0-9
                    or 65 <= c <= 90  # A-Z
                    or 97 <= c <= 122  # a-z
                    or c in (45, 95)  # -_
                ):
                    continue
                raise InvalidHeaders("Invalid header name")
            name = name.strip().lower().decode("ascii")
            if any((c < 32 and c != 9) or c == 127 for c in value):
                raise InvalidHeaders("Invalid header value")
            if name == "content-length":
                value = int(value.strip())
            else:
                value = value.strip().decode("ascii")
            if name not in headers and value:
                headers[name] = value
            elif value:
                headers[name] += ", " + value  # Combined field value
        return headers

    @staticmethod
    def _get_mp_boundary(headers: dict) -> str:
        """
        Determine from the headers if a request is multipart,
        and return the boundary value.
        """
        content_type = headers.get("content-type")
        if not content_type or not content_type.lower().startswith("multipart/"):
            return None

        parts = content_type.split(";")
        for part in parts[1:]:
            if "=" not in part:
                continue
            key, value = part.strip().split("=", 1)

            if key.strip().lower() != "boundary":
                continue
            value = value.strip()

            if value.startswith('"'):
                if len(value) < 2 or not value.endswith('"'):
                    raise InvalidHeaders()
                value = value[1:-1]
            elif value.endswith('"'):
                raise InvalidHeaders()

            if not value:
                raise InvalidHeaders()
            return value
        raise InvalidHeaders()

    @classmethod
    def _parse_body_part(cls, part: memoryview) -> tuple[dict, bytes]:
        """
        Parse part headers and body and return them as a tuple.
        """
        blank_idx = -1
        for i in range(len(part) - 3):
            if part[i : i + 4] == b"\r\n\r\n":
                blank_idx = i
                break
        if blank_idx == -1:
            raise InvalidHeaders()
        headers = cls._parse_headers(part[:blank_idx])
        body = part[blank_idx + 4 :]
        return headers, body

    # =========================================
    # Helpers for state machine termination
    # =========================================

    def set_response_header(self, key: bytes, value: bytes):
        """
        Set a response header by key and value.
        :param key: HTTP header key
        :param value: HTTP header value
        """
        key = key.lower()
        if (
            key in self.resp_headers
            and (index := self.resp_headers.index(key)) % 2 == 0
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
        Serialize and wrap the response body with a BytesIO
        object, stored by the resp_handler member. resp_handler
        can be used for writing the body by the transport layer.
        This method also updates the content-type and content-length
        headers. In the case of a HEAD request, the body is omitted.
        :param body: body to be sent in the response
        :param content_type: content-type of the body
        """
        if body is None:
            return
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
        self.set_response_header(b"content-type", content_type.encode("ascii"))
        if self.method != self.HEAD:
            self.resp_handler = BytesIO(body_encoded)

    def do_keep_alive(self):
        """
        Determine if the connection should be kept alive
        depending on the HTTP version and headers sent in the request.
        """
        if self.aborted:
            return False

        connection_tokens = [
            token.strip().lower()
            for token in self.headers.get("connection", "").split(",")
        ]
        return (self.version == b"HTTP/1.0" and "keep-alive" in connection_tokens) or (
            self.version == b"HTTP/1.1" and "close" not in connection_tokens
        )

    def _handle_route_response(self, callback_response: tuple | None):
        """
        Terminate the state machine based on the return value of a
        user-defined route handler. If the handler does not explicitly
        set a status code, default to HTTP 200. If the handler returns
        a response body and content type, set them accordingly.
        """
        if not self.is_terminated():
            self.terminate(200, True)

        if callback_response is None:
            return

        dtype, data = callback_response
        if dtype.startswith("multipart/") and callable(data):
            self.set_response_header(b"transfer-encoding", b"chunked")
            self.generate_multipart_response(data, dtype)
            return

        self.set_response_body(data, content_type=dtype)

    def terminate(self, status_code: int, request_complete: bool = False):
        """
        Regular state machine termination with a specific status code.
        :param status_code: HTTP status code
        :param request_complete: true if the complete request is processed
        """
        self.state = None
        self.status_code = status_code

        if self.version == b"HTTP/1.0" and self.do_keep_alive() and request_complete:
            self.set_response_header(b"connection", b"keep-alive")
        elif (
            self.version == b"HTTP/1.1"
            and not self.do_keep_alive()
            and not request_complete
        ):
            self.set_response_header(b"connection", b"close")

    def abort(self, status_code: int):
        """
        Abort state machine due to runtime errors.
        Reset any header or response body set earlier.
        :param status_code: HTTP status code
        """
        self.aborted = True
        self.resp_headers = []
        if type(self.resp_handler).__name__ in ("FileIO", "BytesIO"):
            self.resp_handler.close()
            self.resp_handler = None
        self.terminate(status_code, False)

    def is_request_empty(self):
        """
        Returns false if the state machine has received any input.
        """
        return self.is_req_empty

    def is_terminated(self):
        """
        Returns true if the state machine is terminated.
        """
        return self.state is None and self.status_code

    def run(self, rx):
        """
        Run the state machine, consuming the content of a request buffer (rx).
        Unlike individual states, this method does not raise an exception.
        This method yields on every state transition allowing the calling side
        to flush the response buffer.
        """
        if self.is_terminated():
            return
        try:
            while not self.is_terminated():
                self.state(rx)
                yield
        except BufferFullError:
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
            logging.warning(__name__ + f"._run_state_machine: {e}")
            self.abort(500)
            self.set_response_body(str(e).encode("ascii"))

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
        self.state = self._route_request_st

    def _route_request_st(self, _):
        """
        Route requests based on registered endpoints.
        If no endpoint is registered, fall back to file serving.
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
                self.set_response_header(b"allow", b", ".join(supported_methods))
                self.terminate(204, True)
                return
            if self.has_payload():
                if self.method in (self.GET, self.HEAD):
                    raise MalformedRequest()
                if mp_boundary := self._get_mp_boundary(self.headers):
                    # Request body is multipart
                    self.mp_boundary = mp_boundary.encode("ascii")
                    self.state = self._start_multipart_parser_st
                elif self.is_chunked():
                    # Request body is chunked
                    if "content-length" in self.headers:
                        # Ignore content-length as per RFC 9112,
                        # chunked transfer-encoding takes precedence
                        pass
                    self.state = self._recv_chunk_size_st
                else:
                    self.state = self._recv_payload_st
            else:
                self.state = self._app_endpoint_st
            return

        # Request does not have a registered endpoint
        if (
            self._has_endpoint(self.url)
            and self._get_callback(self.method, self.url) is None
        ):
            supported_methods = self._supported_methods(self.url)
            self.set_response_header(b"allow", b", ".join(supported_methods))
            self.terminate(405)
            return
        # Fallback: serve file
        if self.method in (self.GET, self.HEAD):
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
            self.state = self._app_endpoint_st

    def _recv_payload_st(self, rx):
        """
        State for receiving the request body.
        """
        if self.headers["content-length"] > rx.size():
            return
        self.state = self._app_endpoint_st

    def _app_endpoint_st(self, rx):
        """
        Process a request by registered callback functions.
        HEAD requests are temporarily mapped to GET for routing and callback execution,
        but the response body is not sent back.
        """
        method = self.GET if self.method == self.HEAD else self.method
        callback = self._get_callback(self.url, method)
        if self.has_payload():
            if self.is_chunked():
                if self.recv_chunk_size:
                    callback_response = callback(
                        self, bytes(rx.peek(self.recv_chunk_size))
                    )
                    self._consume_payload(rx, self.recv_chunk_size + 2)
                    if not self.is_terminated():
                        self.state = self._recv_chunk_size_st
                        return
                else:
                    # Last chunk, callback with empty body to signal end of request body
                    callback_response = callback(self, b"")
                    self._consume_payload(rx, self.recv_chunk_size + 2, last=True)
            else:
                callback_response = callback(
                    self, bytes(rx.peek(self.headers["content-length"]))
                )
                self._consume_payload(rx, self.headers["content-length"], last=True)
        else:
            callback_response = callback(self, b"")

        self._handle_route_response(callback_response)

    def _fs_retrieve_st(self, _):
        """
        State for retrieving a file under /www.
        /www is prepended to the path by default.
        """
        if self.url == b"/":
            target_path = "/www/index.html"
        else:
            target_path = "/www" + self.url.decode("ascii")

        norm_path = helpers.normalize_path(target_path)
        is_path_served = helpers.is_norm_path_served(
            norm_path, get_config(CONF_HTTP_SERVED_PATHS)
        )

        try:
            if not is_path_served:
                stat(norm_path)
                self.terminate(403, True)
                return

            try:
                extension = target_path.rsplit(".", 1)[-1]
                content_type = self._lookup(
                    self.CONTENT_TYPES, extension.encode("ascii")
                )
            except ValueError:
                content_type = self._lookup(self.CONTENT_TYPES, b"raw")

            self.set_response_header(
                b"content-length", str(stat(norm_path)[6]).encode("ascii")
            )
            self.set_response_header(b"content-type", content_type)
            self.terminate(200, True)
            if self.method != self.HEAD:
                self.resp_handler = open(norm_path, "rb")  # pylint: disable=R1732
            return
        except OSError:
            self.terminate(404, True)

    def _start_multipart_parser_st(self, rx):  # pylint: disable=W0613
        """
        Initial state for processing multipart requests (placeholder).
        """
        self.abort(503)

    def generate_multipart_response(self, callback, dtype):  # pylint: disable=W0613
        """
        Generate multipart response depening on the exact content type (placeholder).
        """
        self.abort(503)


def enable_optional_features():
    """
    Enable related optional features, set in the config.
    """
    if get_config(CONF_HTTP_MULTIPART):
        from pyrobusta.protocol import http_multipart

        http_multipart.apply_patches()

    if get_config(CONF_HTTP_FILES_API):
        from pyrobusta.protocol import http_file_server

        http_file_server.apply_patches()
