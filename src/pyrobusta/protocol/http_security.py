"""
This module adds browser security hardening headers.
"""

from pyrobusta.utils.patch import add_method


def _apply_security_headers(self):
    """
    Apply default HTTP security headers for browser hardening.
    """
    if not self.get_response_header(b"x-content-type-options"):
        self.set_response_header(b"x-content-type-options", b"nosniff")

    if not self.get_response_header(b"content-security-policy"):
        self.set_response_header(
            b"content-security-policy",
            b"default-src 'self';"
            b"script-src 'self';"
            b"style-src 'self' 'unsafe-inline';"
            b"object-src 'none';"
            b"base-uri 'self';"
            b"frame-ancestors 'none'",
        )

    if not self.get_response_header(b"referrer-policy"):
        self.set_response_header(
            b"referrer-policy",
            b"no-referrer",
        )


def apply_patches(cls):
    """
    Apply patches for security headers.
    """
    add_method(cls, _apply_security_headers)
