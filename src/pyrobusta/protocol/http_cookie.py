"""
CSRF protection for HTTP requests.
"""

import os
import binascii

from time import ticks_add, ticks_diff, ticks_ms
from pyrobusta.utils.iam import IAMDatabase, USER_SECRET
from pyrobusta.utils.crypto import (
    HmacSha256,
    create_signed_token,
    verify_signed_token,
)

_NONCE_SIZE = 16
_SESSION_INFO = b"session"
_CSRF_INFO = b"csrf"


def create_session_cookie(username: str, secret: bytes, ttl_sec: int, secure: bool):
    """
    Create a signed session cookie for a user with a given TTL (time-to-live).
    """
    # Format (hex encoded): <username:expiry_tick:nonce>.<signature>
    payload = b":".join(
        (
            username.encode(),
            str(ticks_add(ticks_ms(), ttl_sec * 1000)).encode(),
            binascii.hexlify(os.urandom(_NONCE_SIZE)),
        )
    )
    session_subkey = HmacSha256(secret).digest(_SESSION_INFO)
    cookie = create_signed_token(session_subkey, payload)
    cookie = (
        b"session="
        + cookie
        + b"; max-age="
        + str(ttl_sec).encode()
        + b"; path=/; samesite=strict; httponly"
    )
    if secure:
        cookie += b"; secure"
    return cookie


def verify_session_cookie(session_cookie: bytes, auth_provider: IAMDatabase):
    """
    Verify a session cookie and return user credentials if valid.
    """
    cookie_sep = session_cookie.find(b".")
    if cookie_sep == -1:
        return None

    try:
        cookie_data = binascii.unhexlify(session_cookie[:cookie_sep])
        username, expiry_tick, _ = cookie_data.split(b":")
        username = username.decode().lower()
    except ValueError:
        return None

    user_info = auth_provider.get_user_info(username)
    if not user_info:
        return None

    session_subkey = HmacSha256(user_info[USER_SECRET]).digest(_SESSION_INFO)
    if not verify_signed_token(session_subkey, session_cookie, -1):
        return None

    if ticks_diff(ticks_ms(), int(expiry_tick)) >= 0:
        return None

    return username, user_info


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
