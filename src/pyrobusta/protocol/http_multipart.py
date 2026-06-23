"""
State machine extension for multipart parsing.

This parser does not support chunked multipart requests,
and requires content-length header for multipart parsing.

Requests with a preambule and epilogue are not supported,
and the parser expects the body to start with a boundary
delimiter.
"""

# pylint: disable=W0212,R0401

from pyrobusta.protocol import http
from pyrobusta.utils.helpers import add_method, add_property, patch_extra_property


def generate_multipart_response(self, callback: callable, dtype: str):
    """
    Generate multipart response depening on the exact content type.
    The callback function is called without arguments, and it must return bytes-like objects.
    :param callback: function for part generation, each call generates a separate part
    :param dtype: exact multipart content-type (multipart/*)
    """
    if not callable(callback):
        raise ValueError("Invalid function callback")

    boundary = self.MULTIPART_BOUNDARY
    self.set_response_header(
        b"content-type", dtype.encode("ascii") + b"; boundary=" + boundary
    )
    self.set_response_header(b"transfer-encoding", b"chunked")
    if self.method != self.HEAD:
        self.resp_handler = self._multipart_wrapper_factory(callback, boundary)


def _multipart_wrapper_factory(callback: callable, boundary: bytes):
    """
    Factory method for creating closures that write multipart responses.
    The function callback is called without arguments, and it must return bytes-like objects.
    :param callback: function for part generation, each call generates a separate part
    :param boundary: boundary value
    :return closure: closure to invoke for response generation
    """
    delimiter = b"--" + boundary

    def _multipart_wrapper(tx):
        """
        Write multipart data generated from a callback function's return value.
        - if insufficient buffer space is available, the generator yields control so
        the caller can flush or drain the buffer
        :return bool: true if the stream is completed
        """
        while True:
            part = callback()

            if not part:
                tx.write(delimiter)
                tx.write(b"--\r\n")
                yield True
                return

            content_type, part_body = part
            headers = (
                delimiter
                + b"\r\ncontent-type:"
                + content_type.encode("ascii")
                + b"\r\n\r\n"
            )

            for chunk_part in (headers, part_body, b"\r\n"):
                written = 0
                while written < len(chunk_part):
                    to_write = tx.capacity - tx.size()
                    if not to_write:
                        raise BufferError()
                    chunk_part = chunk_part[written : written + to_write]
                    tx.write(chunk_part)
                    written += len(chunk_part)
                    yield False

    return _multipart_wrapper


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
                raise http.InvalidHeaders()
            value = value[1:-1]
        elif value.endswith('"'):
            raise http.InvalidHeaders()

        if not value:
            raise http.InvalidHeaders()
        return value
    raise http.InvalidHeaders()


def _start_multipart_parser_st(self, rx):
    """
    Initial state for processing multipart requests.
    Chunked requests are not supported, and content-length
    header is required for multipart parsing.
    """
    if not "content-length" in self.headers:
        raise http.InvalidContentLength()

    self.mp_boundary = _get_mp_boundary(self.headers).encode("ascii")

    if (start_delimiter := rx.find(b"\r\n")) == -1:
        return

    if rx.peek(start_delimiter + 2) != self.mp_delimiter:
        raise http.MalformedRequest()
    self._consume_payload(rx, start_delimiter + 2)
    self.mp_is_first = True
    self.mp_is_last = False
    self.state = self._parse_boundary_st


def _parse_boundary_st(self, rx):
    """
    State for parsing multipart boundary delimiter.
    """
    is_intermediate = rx.find(b"\r\n" + self.mp_delimiter) != -1
    is_last = rx.find(b"\r\n" + self.mp_last_delimiter) != -1

    if not is_intermediate and not is_last:
        return

    if is_last and self.content_len_cnt + rx.size() < self.headers["content-length"]:
        return

    self.state = self._parse_complete_part_st


def _parse_complete_part_st(self, rx):
    """
    State for processing complete parts in a multipart request.
    - registered route handler is required to process parts
    """
    next_delimiter = rx.find(b"\r\n--" + self.mp_boundary)
    part = rx.peek(next_delimiter)
    self._consume_payload(rx, next_delimiter + 2)  # Consume leading CRLF
    is_final = (
        rx.size() >= len(self.mp_last_delimiter)
        and rx.peek(len(self.mp_last_delimiter)) == self.mp_last_delimiter
    )

    part_headers, part_body = http.HttpEngine._parse_body_part(part)
    handler = http.HttpEngine._get_handler(self.url, self.method)

    # Process complete part
    if not is_final:
        handler_response = handler(self, (part_headers, part_body))
        if rx.peek(len(self.mp_delimiter)) != self.mp_delimiter:
            raise http.MalformedRequest()
        self._consume_payload(rx, len(self.mp_delimiter))
        self.mp_is_first = False
        if not self.state == self._terminal_st:
            # Proceed to next part if there is no early termination
            self.state = self._parse_boundary_st
        elif handler_response:
            self._handle_route_response(handler_response)
        return

    # Process last part
    self._consume_payload(rx, len(self.mp_last_delimiter))

    if (
        self.content_len_cnt + 2 == self.headers["content-length"]
        and rx.peek(2) == b"\r\n"
    ):
        # Consume optional trailing CRLF
        self._consume_payload(rx, 2, last=True)
    else:
        self._consume_payload(rx, 0, last=True)

    self.mp_is_last = True
    handler_response = handler(self, (part_headers, part_body))

    self._handle_route_response(handler_response)


def apply_patches():
    """
    Apply patches to class attributes for multipart parsing.
    """

    def mp_delimiter(self):
        if self.mp_boundary is None:
            return None
        return b"--" + self.mp_boundary + b"\r\n"

    def mp_last_delimiter(self):
        if self.mp_boundary is None:
            return None
        return b"--" + self.mp_boundary + b"--"

    add_property(http.HttpEngine, mp_delimiter)
    add_property(http.HttpEngine, mp_last_delimiter)

    patch_extra_property(http.HttpEngine, "mp_boundary")
    patch_extra_property(http.HttpEngine, "mp_is_first")
    patch_extra_property(http.HttpEngine, "mp_is_last")

    add_method(http.HttpEngine, generate_multipart_response)
    add_method(http.HttpEngine, _get_mp_boundary, "static")
    add_method(http.HttpEngine, _multipart_wrapper_factory, "static")
    add_method(http.HttpEngine, _start_multipart_parser_st)
    add_method(http.HttpEngine, _parse_boundary_st)
    add_method(http.HttpEngine, _parse_complete_part_st)

    http.HttpEngine.MULTIPART_BOUNDARY = b"pyrobusta-boundary"
