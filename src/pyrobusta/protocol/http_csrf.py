"""
CSRF protection for HTTP requests.
"""

import os

from pyrobusta.utils.crypto import HmacSha256, verify_signed_token, create_signed_token

_NONCE_SIZE = 16
_CSRF_INFO = b"csrf"


def create_csrf_cookie(secret: bytes, secure: bool):
    """
    Create a CSRF token cookie with a secret used for
    cryptographic signing.
    """
    payload = os.urandom(_NONCE_SIZE)
    csrf_subkey = HmacSha256(secret).digest(_CSRF_INFO)
    csrf_token = create_signed_token(csrf_subkey, payload)
    cookie = b"csrf-token=" + csrf_token + b"; path=/; samesite=strict"
    if secure:
        cookie += b"; secure"
    return cookie


def verify_csrf_cookie(cookie: bytes, csrf_header: bytes, secret: bytes):
    """
    Verify a CSRF token cookie against the CSRF header.
    The CSRF token is verified with the secret used for signing.
    """
    if not cookie or not csrf_header:
        return False
    csrf_sep = csrf_header.find(b".")
    if csrf_sep == -1:
        return False
    if cookie != csrf_header:
        return False
    csrf_subkey = HmacSha256(secret).digest(_CSRF_INFO)
    if not verify_signed_token(csrf_subkey, csrf_header, _NONCE_SIZE):
        return False
    return True
