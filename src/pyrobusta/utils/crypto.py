"""
Utility functions for cryptography operations.
"""

import asyncio
import binascii
import hashlib
import math


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


def create_signed_token(secret: bytes, payload: bytes):
    """
    Create a signed token with a payload.
    """
    hmac = HmacSha256(secret)
    signature = binascii.hexlify(hmac.digest(payload))
    return binascii.hexlify(payload) + b"." + signature


def verify_signed_token(secret: bytes, token: bytes, payload_size: int):
    """
    Verify a signed token with a payload.
    The size of the payload is verified if payload_size != -1.
    """
    try:
        sep = token.find(b".")
        if sep == -1:
            return False
        data = binascii.unhexlify(token[:sep])
        if payload_size != -1 and len(data) != payload_size:
            return False
        request_signature = binascii.unhexlify(token[sep + 1 :])
        hmac = HmacSha256(secret)
        expected_signature = hmac.digest(data)
    except (ValueError, binascii.Error):
        return False
    return constant_time_equal(request_signature, expected_signature)


def validate_password(password: str, min_length: int = 16, min_entropy: float = 80.0):
    """
    Validate user password complexity.

    Entropy estimate assumes the password was generated randomly
    from PASSWORD_ALPHABET.
    """
    password_alphabet = (
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "abcdefghijklmnopqrstuvwxyz"
        "0123456789"
        "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
    )

    if len(password) < min_length:
        raise ValueError(f"Password must be at least {min_length} characters")

    for char in password:
        if char not in password_alphabet:
            raise ValueError("Password contains unsupported characters")

    entropy = len(password) * math.log2(len(password_alphabet))

    if entropy < min_entropy:
        raise ValueError(
            f"Password entropy too low ({entropy:.1f} bits, "
            f"minimum {min_entropy:.1f} bits)"
        )


def pbkdf2_validate_arguments(iterations, dklen):
    """
    Validate PBKDF2 arguments.
    """
    if iterations <= 0:
        raise ValueError("iterations must be positive")

    if dklen <= 0:
        raise ValueError("dklen must be positive")

    if dklen > (2**dklen - 1) * dklen:
        raise ValueError("derived key too long")


def pbkdf2_sha256(password: bytes, salt: bytes, iterations: int, dklen: int = 32):
    """
    Compute PBKDF2-SHA256-based password hash,
    based on RFC8018.
    """
    hmac = HmacSha256(password)
    output = bytearray()
    block_number = 1
    pbkdf2_validate_arguments(iterations, dklen)

    while len(output) < dklen:
        # U1 = PRF(password, salt || INT(block))
        u = hmac.digest(salt + block_number.to_bytes(4, "big"))
        t = bytearray(u)
        # U2 ... Uc
        for _ in range(iterations - 1):
            u = hmac.digest(u)
            for i, _ in enumerate(t):
                t[i] ^= u[i]
        output.extend(t)
        block_number += 1
    return bytes(output[:dklen])


async def a_pbkdf2_sha256(
    password: bytes, salt: bytes, iterations: int, dklen: int = 32
):
    """
    Compute PBKDF2-SHA256-based password hash asynchronously,
    based on RFC8018.
    """
    hmac = HmacSha256(password)
    output = bytearray()
    block_number = 1
    pbkdf2_validate_arguments(iterations, dklen)

    while len(output) < dklen:
        # U1 = PRF(password, salt || INT(block))
        u = hmac.digest(salt + block_number.to_bytes(4, "big"))
        t = bytearray(u)
        # U2 ... Uc
        for i in range(iterations - 1):
            u = hmac.digest(u)
            for j, _ in enumerate(t):
                t[j] ^= u[j]
            if i % 100 == 0:
                await asyncio.sleep(0.001)  # pylint: disable=E1101
        output.extend(t)
        block_number += 1
    return bytes(output[:dklen])
