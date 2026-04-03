"""
State machine extension for multipart parsing.
"""

# pylint: disable=W0212,R0401

from pyrobusta.protocol import http
from pyrobusta.utils.helpers import add_method


def _generate_multipart_response(self, _, tx, callback, dtype):
    """Generate multipart response depening on the exact content type"""
    if type(callback).__name__ not in ("function", "closure"):
        self.on_failure(tx, b"Invalid response handler")
        return
    self.terminate(200, dtype)
    boundary = self.MULTIPART_BOUNDARY
    self._set_response_header(b"content-type", dtype + b"; boundary=" + boundary)
    self._write_response_head(tx, None)
    if self.method != self.HEAD:
        return self._multipart_wrapper_factory(callback, boundary)


def _multipart_wrapper_factory(callback, boundary: bytes):
    """
    Factory method for creating closures that write multipart responses
    :param callback: function without arguments, must return bytes-like objects
    :param content_type: content type of body parts
    :param boundary: boundary value
    :return closure: closure to invoke for response generation
    """
    delimiter = b"--" + boundary

    def _multipart_wrapper(tx):
        """
        Write multipart data generated from a callback's return value
        - if insufficient buffer space is available, the generator yields control so
        the caller can flush or drain the buffer
        :return bool: true if the stream is completed
        """
        while True:
            tx.write(delimiter)
            part = callback()
            if not part:
                tx.write(b"--")
                yield True
            content_type, part_body = part
            tx.write(b"\r\n")
            tx.write(b"content-type:")
            tx.write(content_type.encode("ascii"))
            tx.write(b"\r\n\r\n")
            written = 0
            while written < len(part_body):
                to_write = tx.capacity - tx.size()
                if not to_write:
                    raise BufferError()
                tx.write(part_body[written : written + to_write])
                written += to_write
                yield False
            tx.write(b"\r\n")

    return _multipart_wrapper


def _start_multipart_parser_st(self, rx, tx):
    """Initial state for processing multipart requests"""
    if not http.HttpEngine.CONTENT_LENGTH in self.headers:
        self.on_client_error(tx, http.HttpEngine.CONTENT_LENGTH_ERROR)
        return
    if (start_delimiter := rx.find(b"\r\n")) == -1:
        return
    self.mp_delimiter = b"--" + self.mp_boundary + b"\r\n"
    self.mp_last_delimiter = b"--" + self.mp_boundary + b"--"
    if rx.peek(start_delimiter + 2) != self.mp_delimiter:
        self.on_client_error(tx, http.HttpEngine.MULTIPART_BOUNDARY_ERROR)
        return
    rx.consume(start_delimiter + 2)
    self.content_len_cnt += start_delimiter + 2
    self.state = self._parse_boundary_st


def _parse_boundary_st(self, rx, _):
    """State for parsing multipart boundary delimiter"""
    if (
        rx.find(b"\r\n" + self.mp_delimiter) == -1
        and rx.find(b"\r\n" + self.mp_last_delimiter) == -1
    ):
        return
    self.state = self._parse_complete_part_st


def _parse_complete_part_st(self, rx, tx):
    """
    State for processing complete parts in a multipart request
    - registered callback is required to process parts
    """
    next_delimiter = rx.find(b"\r\n--" + self.mp_boundary)
    part = rx.peek(next_delimiter)
    rx.consume(next_delimiter + 2)  # Consume leading CRLF
    self.content_len_cnt += next_delimiter + 2
    is_final = rx.peek(len(self.mp_last_delimiter)) == self.mp_last_delimiter
    # Validate part and content-length
    if self.headers[http.HttpEngine.CONTENT_LENGTH] < self.content_len_cnt:
        self.on_client_error(tx, http.HttpEngine.CONTENT_LENGTH_ERROR)
        return
    try:
        part_headers, part_body = http.HttpEngine._parse_body_part(part)
    except http.HeaderParsingError:
        self.on_client_error(tx, http.HttpEngine.HEADER_ERROR)
        return
    callback = http.HttpEngine._get_callback(self.url, self.method)
    # Process complete part
    if not is_final:
        callback(self, (part_headers, part_body))
        if rx.peek(len(self.mp_delimiter)) != self.mp_delimiter:
            self.on_client_error(tx, http.HttpEngine.MULTIPART_BOUNDARY_ERROR)
            return
        rx.consume(len(self.mp_delimiter))
        self.content_len_cnt += len(self.mp_delimiter)
        self.mp_is_first = False
        self.state = self._parse_boundary_st
        return
    # Process last part
    rx.consume(len(self.mp_last_delimiter))
    self.content_len_cnt += len(self.mp_last_delimiter)
    if (
        self.headers[http.HttpEngine.CONTENT_LENGTH] != self.content_len_cnt
        and self.content_len_cnt + rx.size()
        != self.headers[http.HttpEngine.CONTENT_LENGTH]
    ):
        self.on_client_error(tx, http.HttpEngine.CONTENT_LENGTH_ERROR)
        return
    self.mp_is_last = True
    dtype, data = callback(self, (part_headers, part_body))
    self.terminate(200, dtype.encode(http.HttpEngine.ASCII))
    return self._generate_response(tx, data)


def apply_patches():
    """
    Apply patches to class attributes for multipart parsing.
    """
    orig_init = http.HttpEngine.__init__

    def new_init(self, *args, **kwargs):
        orig_init(self, *args, **kwargs)
        self.mp_is_first = True
        self.mp_is_last = False
        self.mp_delimiter = None
        self.mp_last_delimiter = None

    http.HttpEngine.__init__ = new_init

    add_method(http.HttpEngine, _generate_multipart_response)
    add_method(http.HttpEngine, _multipart_wrapper_factory, "static")
    add_method(http.HttpEngine, _start_multipart_parser_st)
    add_method(http.HttpEngine, _parse_boundary_st)
    add_method(http.HttpEngine, _parse_complete_part_st)
