"""
Utility functions for cryptography operations.
"""

import binascii
import hashlib
import os


class HmacSha256:
    # pylint: disable=R0903
    """
    Helper class for SHA-256-based Hashed MAC (HMAC)
    computation, based on RFC 2104.
    """

    def __init__(self, key: bytes):
        if len(key) > 64:
            key = hashlib.sha256(key).digest()
        if len(key) < 64:
            key = key + b"\x00" * (64 - len(key))
        self.ipad = bytes(x ^ 0x36 for x in key)
        self.opad = bytes(x ^ 0x5C for x in key)

    def digest(self, msg: bytes):
        """
        Calculate the HMAC digest of a message.
        """
        inner = hashlib.sha256()
        inner.update(self.ipad)
        inner.update(msg)
        outer = hashlib.sha256()
        outer.update(self.opad)
        outer.update(inner.digest())
        return outer.digest()


def constant_time_equal(a: bytes, b: bytes):
    """
    Constant time comparison to prevent timing attacks.
    """
    if len(a) != len(b):
        return False
    diff = 0
    for x, y in zip(a, b):
        diff |= x ^ y
    return diff == 0


def create_signed_token(secret: bytes, nonce_size: int = 16):
    """
    Create a signed token containing only a random nonce.
    """
    nonce = os.urandom(nonce_size)
    data = nonce
    hmac = HmacSha256(secret)
    signature = binascii.hexlify(hmac.digest(data))
    return binascii.hexlify(data) + b"." + signature


def verify_signed_token(secret: bytes, token: bytes, nonce_size: int = 16):
    """
    Verify a signed token containing only a random nonce.
    """
    try:
        sep = token.find(b".")
        if sep == -1:
            return False
        data = binascii.unhexlify(token[:sep])
        if len(data) != nonce_size:
            return False
        request_signature = binascii.unhexlify(token[sep + 1 :])
        hmac = HmacSha256(secret)
        expected_signature = hmac.digest(data)
    except (ValueError, binascii.Error):
        return False
    return constant_time_equal(request_signature, expected_signature)
