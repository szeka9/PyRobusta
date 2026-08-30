"""
Module for HTTP Basic Authentication.

This module overrides the auth placeholder HttpEngine._handle_auth_st(),
and applies the basic authentication scheme with CSRF protection.
"""

# pylint: disable=W0212,R0401

import asyncio
import binascii
import os

from pyrobusta.protocol.http_cookie import (
    create_session_cookie,
    verify_session_cookie,
    create_csrf_cookie,
    verify_csrf_cookie,
)
from pyrobusta.utils.patch import add_method, patch_extra_property
from pyrobusta.utils.crypto import constant_time_equal, pbkdf2_sha256, a_pbkdf2_sha256
from pyrobusta.utils.iam import (
    NO_POLICY,
    IAMDatabase,
    ROLE_MASK,
    PASS_HASH,
    PASS_SALT,
    PASS_ITER,
    USER_SECRET,
)
from pyrobusta.utils import logging

_DUMMY_ITER = 5000
_DUMMY_SALT = os.urandom(16)
_DUMMY_HASH = pbkdf2_sha256(os.urandom(20), _DUMMY_SALT, 100)

_BROWSER_SECURITY = None
_SESSIONS_ENABLED = None
_SESSION_TTL_SEC = None
_AUTH_PROVIDER = None


class AuthPromise:
    # pylint: disable=R0903
    """
    Helper class for the asynchronous computation of PBKDF2 password hashing.
    """

    __slots__ = ("done", "result")

    def __init__(self, authenticator, username, password):
        self.done = None
        self.result = None

        asyncio.create_task(authenticator(self, username, password))


async def _auth_user(promise, username, password):
    user_info = _AUTH_PROVIDER.get_user_info(username)
    stored_hash = user_info[PASS_HASH] if user_info else _DUMMY_HASH

    if user_info:
        password_hash = await a_pbkdf2_sha256(
            password,
            user_info[PASS_SALT],
            user_info[PASS_ITER],
            len(user_info[PASS_HASH]),
        )
    else:
        password_hash = await a_pbkdf2_sha256(
            password, _DUMMY_SALT, _DUMMY_ITER, len(_DUMMY_HASH)
        )

    hash_ok = constant_time_equal(password_hash, stored_hash)
    user_ok = user_info is not None

    if not (user_ok and hash_ok):
        logging.info("authentication failed for user=[%s]", username)
    else:
        promise.result = (username, user_info)
    promise.done = True


def _handle_auth_st(self, _):
    # Determine security policy
    is_public = False
    method = self.method.decode("ascii")
    url = self.url.decode("ascii")

    policy = _AUTH_PROVIDER.get_access_policies(url)
    if not policy:
        self.state = self._handle_auth_header_st
        return

    if method not in policy:
        if policy.get("*") == NO_POLICY:
            is_public = True
    elif policy[method] == NO_POLICY:
        is_public = True

    if is_public:
        self.state = self._route_request_st
    else:
        self.state = self._handle_auth_header_st


def parse_auth_headers(http_ctx):
    """
    Parse authorization headers and return
    a username and password.
    """
    # Protocol validation
    auth_header = http_ctx.headers.get("authorization")
    if not auth_header or auth_header[:6].lower() != "basic ":
        return None

    # Decoding
    auth_header = auth_header[6:].strip()
    try:
        auth_header = binascii.a2b_base64(auth_header).decode("ascii")
    except binascii.Error:
        return None

    # Authentication
    user_sep = auth_header.find(":")
    if user_sep < 0:
        return None

    username = auth_header[:user_sep].lower()
    password = auth_header[user_sep + 1 :].strip().encode("ascii")
    return username, password


def _handle_auth_header_st(self, _):
    method = self.method.decode("ascii")
    url = self.url.decode("ascii")
    is_session = False
    user_data = None

    # Authentication
    is_session = (
        _SESSIONS_ENABLED
        and (session_cookie := self.get_cookie("session"))
        and (
            user_data := verify_session_cookie(
                session_cookie.encode("ascii"), _AUTH_PROVIDER
            )
        )
    )

    if not is_session:
        if not self.auth_promise:
            credentials = parse_auth_headers(self)
            if not credentials:
                self.set_response_header(b"WWW-Authenticate", b'Basic realm="Device"')
                self.terminate(401)
                return None
            username, password = credentials
            self.auth_promise = AuthPromise(_auth_user, username, password)
        if not self.auth_promise.done:
            return self.auth_promise
        user_data = self.auth_promise.result

    if not user_data:
        self.set_response_header(b"WWW-Authenticate", b'Basic realm="Device"')
        self.terminate(401)
        return None

    username, user_info = user_data

    # CSRF validation, cookie setting
    if _BROWSER_SECURITY:
        if self.method not in (
            self.GET,
            self.HEAD,
            self.OPTIONS,
        ):
            if not verify_csrf_cookie(
                self.get_cookie("csrf-token", "").encode("ascii"),
                self.headers.get("x-csrf-token", "").encode("ascii"),
                user_info[USER_SECRET],
            ):
                self.terminate(403)
                return None
        elif self.method in (self.GET, self.HEAD):
            if self.get_cookie("csrf-token") is None:
                cookie = create_csrf_cookie(user_info[USER_SECRET], self.TLS)
                self.set_response_header(b"set-cookie", cookie, override=False)

    # Session creation
    if not is_session and _SESSIONS_ENABLED:
        session_cookie = create_session_cookie(
            username, user_info[USER_SECRET], _SESSION_TTL_SEC, self.TLS
        )
        self.set_response_header(b"set-cookie", session_cookie, override=False)

    # Authorization
    policy = _AUTH_PROVIDER.get_access_policies(url)

    if not policy:
        allowed_roles = 0
    elif method not in policy:
        allowed_roles = policy.get("*", 0)
    else:
        allowed_roles = policy[method]

    if (allowed_roles & user_info[ROLE_MASK]) == 0:
        self.terminate(403)
        return None

    self.state = self._route_request_st
    return None


def apply_patches(cls, config, auth_provider: IAMDatabase):
    """
    Apply patches to class attributes for HTTP basic authentication.
    """
    if auth_provider is None:
        raise ValueError

    if not config.tls and config.http_auth:
        insecure_auth_msg = "authentication turned on without TLS"
        if config.http_insecure_auth:
            logging.warning(insecure_auth_msg)
        else:
            raise ValueError(insecure_auth_msg)

    if not config.http_browser_security:
        logging.warning(
            "CSRF protection is disabled; "
            "authenticated clients are vulnerable to CSRF attacks"
        )

    # pylint: disable=W0603
    global _AUTH_PROVIDER, _BROWSER_SECURITY, _SESSIONS_ENABLED, _SESSION_TTL_SEC
    _AUTH_PROVIDER = auth_provider
    _BROWSER_SECURITY = config.http_browser_security
    _SESSIONS_ENABLED = config.http_sessions
    _SESSION_TTL_SEC = config.http_session_ttl_sec

    add_method(cls, _handle_auth_st)
    add_method(cls, _handle_auth_header_st)
    patch_extra_property(cls, "auth_promise")
