"""
This module adds browser security hardening headers.
"""


def _apply_security_headers(engine):
    """
    Apply default HTTP security headers for browser hardening.
    """
    if engine.get_response_header(b"content-type") is None:
        return

    if not engine.get_response_header(b"x-content-type-options"):
        engine.set_response_header(b"x-content-type-options", b"nosniff")

    if not engine.get_response_header(b"content-security-policy"):
        engine.set_response_header(
            b"content-security-policy",
            b"default-src 'self'; "
            b"script-src 'self'; "
            b"style-src 'self' 'unsafe-inline'; "
            b"object-src 'none'; "
            b"base-uri 'self'; "
            b"frame-ancestors 'none'",
        )

    if not engine.get_response_header(b"referrer-policy"):
        engine.set_response_header(
            b"referrer-policy",
            b"no-referrer",
        )


def apply_patches(cls, *_):
    """
    Apply patches for security headers.
    """
    cls.POST_HOOKS.append(_apply_security_headers)
