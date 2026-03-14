from web import WebEngine, HeaderParsingError


def add_method(cls, type="instance"):
    def decorator(func):
        if type == "instance":
            setattr(cls, func.__name__, func)
        elif type == "staticmethod":
            setattr(cls, func.__name__, staticmethod(func))
        elif type == "classmethod":
            setattr(cls, func.__name__, classmethod(func))
        else:
            raise ValueError("Invalid type")
        return func

    return decorator


@add_method(WebEngine, "staticmethod")
def _multipart_wrapper_factory(callback, content_type: bytes, boundary: bytes):
    """
    Factory method for creating closures that write multipart responses
    :param callback: function without arguments, must return bytes-like objects
    :param content_type: content type of body parts
    :param boundary: boundary value
    :return closure: closure to invoke for response generation
    """
    boundary = b"--" + boundary
    content_type_header = b"content-type: %s\r\n\r\n" % content_type

    def _multipart_wrapper(tx):
        """
        Write multipart data generated from a callback's return value
        - if insufficient buffer space is available, the generator yields control so
        the caller can flush or drain the buffer
        :return bool: true if the stream is completed
        """
        while True:
            tx.write(boundary)
            part_body = callback()
            if not part_body:
                tx.write(b"--")
                yield True
            tx.write(b"\r\n")
            tx.write(content_type_header)
            written = 0
            while written < len(part_body):
                to_write = tx.capacity - tx.size()
                if not to_write:
                    raise BufferError("Cannot write multipart response to buffer")
                tx.write(part_body[written : written + to_write])
                written += to_write
                yield False
            tx.write(b"\r\n")

    return _multipart_wrapper


@add_method(WebEngine)
def _start_multipart_parser_st(self, rx, tx):
    """Initial state for processing multipart requests"""
    if not WebEngine.CONTENT_LENGTH in self.headers:
        self.on_client_error(tx, WebEngine.CONTENT_LENGTH_ERROR)
        return
    if (start_delimiter := rx.find(b"\r\n")) == -1:
        return
    self.mp_delimiter = b"--" + self.mp_boundary + b"\r\n"
    self.mp_closing_delimiter = b"--" + self.mp_boundary + b"--"
    if rx.peek(start_delimiter + 2) != self.mp_delimiter:
        self.on_client_error(tx, WebEngine.MULTIPART_BOUNDARY_ERROR)
        return
    rx.consume(start_delimiter + 2)
    self.content_length_cnt += start_delimiter + 2
    self.state = self._parse_boundary_st


@add_method(WebEngine)
def _parse_boundary_st(self, rx, _):
    """State for parsing multipart boundary delimiter"""
    if (
        rx.find(b"\r\n" + self.mp_delimiter) == -1
        and rx.find(b"\r\n" + self.mp_closing_delimiter) == -1
    ):
        return
    self.state = self._parse_complete_part_st


@add_method(WebEngine)
def _parse_complete_part_st(self, rx, tx):
    """
    State for processing complete parts in a multipart request
    - registered load module callback is required to process parts
    """
    next_delimiter = rx.find(b"\r\n--" + self.mp_boundary)
    part = rx.peek(next_delimiter)
    rx.consume(next_delimiter + 2)  # Consume leading CRLF
    self.content_length_cnt += next_delimiter + 2
    is_final = rx.peek(len(self.mp_closing_delimiter)) == self.mp_closing_delimiter
    # Validate part and content-length
    if self.headers[WebEngine.CONTENT_LENGTH] < self.content_length_cnt:
        self.on_client_error(tx, WebEngine.CONTENT_LENGTH_ERROR)
        return
    try:
        part_headers, part_body = WebEngine._parse_body_part(part)
    except HeaderParsingError:
        self.on_client_error(tx, WebEngine.HEADER_ERROR)
        return
    callback = WebEngine.ENDPOINTS[self.url][self.method]
    # Process complete part
    if not is_final:
        callback(part_headers, part_body, first=self.mp_first_part, last=False)
        if rx.peek(len(self.mp_delimiter)) != self.mp_delimiter:
            self.on_client_error(tx, WebEngine.MULTIPART_BOUNDARY_ERROR)
            return
        rx.consume(len(self.mp_delimiter))
        self.content_length_cnt += len(self.mp_delimiter)
        self.mp_first_part = False
        self.state = self._parse_boundary_st
        return
    # Process last part
    rx.consume(len(self.mp_closing_delimiter))
    self.content_length_cnt += len(self.mp_closing_delimiter)
    if (
        self.headers[WebEngine.CONTENT_LENGTH] != self.content_length_cnt
        and self.content_length_cnt + rx.size()
        != self.headers[WebEngine.CONTENT_LENGTH]
    ):
        self.on_client_error(tx, WebEngine.CONTENT_LENGTH_ERROR)
        return
    dtype, data = callback(part_headers, part_body, first=self.mp_first_part, last=True)
    self.terminate(200, dtype.encode(WebEngine.ASCII))
    return self._generate_response(tx, data)
