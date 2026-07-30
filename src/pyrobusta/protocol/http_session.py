"""
HTTP session management for authentication.
"""

import os
import binascii

from pyrobusta.utils.clock import ticks_add, ticks_diff, ticks_ms
from pyrobusta.utils.config import get_config, CONF_TLS
from pyrobusta.utils.iam import IAMDatabase, USER_SECRET
from pyrobusta.utils.crypto import (
    HmacSha256,
    create_signed_token,
    verify_signed_token,
)

_NONCE_SIZE = 16
_SESSION_INFO = b"session"


def create_cookie(username: str, secret: bytes, ttl_sec: int):
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
    if get_config(CONF_TLS):
        cookie += b"; secure"
    return cookie


def verify_cookie(session_cookie: bytes, auth_provider: IAMDatabase):
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
