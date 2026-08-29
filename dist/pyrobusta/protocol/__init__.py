"""
Common exceptions
"""


class InvalidHeaders(ValueError):
    """Exception for invalid HTTP/MIME headers."""

    pass


class InvalidContentLength(ValueError):
    """Exception for content-length related erros."""

    pass


class MalformedRequest(ValueError):
    """Exception for malformed requests."""

    pass
