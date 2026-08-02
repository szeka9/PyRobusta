"""
Module for HTTP Basic Authentication.

This module overrides the auth placeholder HttpEngine._handle_auth_st(),
and applies the basic authentication scheme with CSRF protection.
"""

# pylint: disable=W0212,R0401

import binascii
import os

from pyrobusta.protocol.http import HttpEngine
from pyrobusta.protocol import http_session
from pyrobusta.protocol import http_csrf
from pyrobusta.utils.patch import add_method
from pyrobusta.utils.crypto import (
    constant_time_equal,
    pbkdf2_sha256,
)
from pyrobusta.utils.config import (
    get_config,
    CONF_HTTP_AUTH,
    CONF_HTTP_AUTH_MODE,
    CONF_HTTP_INSECURE_AUTH,
    CONF_HTTP_SESSIONS,
    CONF_HTTP_SESSION_TTL_SEC,
    CONF_TLS,
)
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
_DUMMY_HASH = pbkdf2_sha256(os.urandom(20), _DUMMY_SALT, _DUMMY_ITER)


def _auth_user(self: HttpEngine, auth_provider: IAMDatabase, sessions=False):
    # Session validation
    if sessions and (session_cookie := self.get_cookie("session")):
        if credentials := http_session.verify_cookie(
            session_cookie.encode("ascii"), auth_provider
        ):
            username, user_info = credentials
            is_session = True
            return username, user_info, is_session

    is_session = False

    # Protocol validation
    auth_header = self.headers.get("authorization")
    if not auth_header or auth_header[:6].lower() != "basic ":
        return None

    # Decoding
    auth_header = auth_header[6:].strip()
    try:
        auth_header = binascii.a2b_base64(auth_header).decode()
    except binascii.Error:
        return None

    # Authentication
    user_sep = auth_header.find(":")
    if user_sep < 0:
        return None

    username = auth_header[:user_sep].lower()
    password = auth_header[user_sep + 1 :].strip().encode("ascii")
    user_info = auth_provider.get_user_info(username)
    stored_hash = user_info[PASS_HASH] if user_info else _DUMMY_HASH

    if user_info:
        password_hash = pbkdf2_sha256(
            password,
            user_info[PASS_SALT],
            user_info[PASS_ITER],
            len(user_info[PASS_HASH]),
        )
    else:
        password_hash = pbkdf2_sha256(
            password, _DUMMY_SALT, _DUMMY_ITER, len(_DUMMY_HASH)
        )

    hash_ok = constant_time_equal(password_hash, stored_hash)
    user_ok = user_info is not None

    if not (user_ok and hash_ok):
        logging.info("authentication failed for user=[%s]", username)
        return None

    return username, user_info, is_session


def _handle_auth_st(self, _):
    # Determine security policy
    is_public = False
    method = self.method.decode("ascii")
    url = self.url.decode("ascii")

    policy = self.get_policy(url)
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


def _handle_auth_header_st(self, _):
    method = self.method.decode("ascii")
    url = self.url.decode("ascii")

    # Authentication
    if not (credentials := self._authenticate()):
        self.set_response_header(b"WWW-Authenticate", b'Basic realm="Device"')
        self.terminate(401)
        return
    username, user_info, is_session = credentials

    # CSRF validation, cookie setting
    if get_config(CONF_HTTP_AUTH_MODE) == "browser" and not is_session:
        if self.method not in (
            self.GET,
            self.HEAD,
            self.OPTIONS,
        ):
            if not http_csrf.verify_cookie(
                self.get_cookie("csrf-token", "").encode("ascii"),
                self.headers.get("x-csrf-token", "").encode("ascii"),
                user_info[USER_SECRET],
            ):
                self.terminate(403)
                return
        elif self.method in (self.GET, self.HEAD):
            if self.get_cookie("csrf-token") is None:
                cookie = http_csrf.create_cookie(user_info[USER_SECRET])
                self.set_response_header(b"set-cookie", cookie, override=False)

    # Session creation
    if not is_session and get_config(CONF_HTTP_SESSIONS):
        session_cookie = http_session.create_cookie(
            username, user_info[USER_SECRET], get_config(CONF_HTTP_SESSION_TTL_SEC)
        )
        self.set_response_header(b"set-cookie", session_cookie, override=False)

    # Authorization
    policy = self.get_policy(url)

    if not policy:
        allowed_roles = 0
    elif method not in policy:
        allowed_roles = policy.get("*", 0)
    else:
        allowed_roles = policy[method]

    if (allowed_roles & user_info[ROLE_MASK]) == 0:
        self.terminate(403)
        return

    self.state = self._route_request_st


def apply_patches(auth_provider: IAMDatabase, sessions=False):
    """
    Apply patches to class attributes for HTTP basic authentication.
    """
    if auth_provider is None:
        raise ValueError

    if not get_config(CONF_TLS) and get_config(CONF_HTTP_AUTH):
        insecure_auth_msg = "authentication turned on without TLS"
        if get_config(CONF_HTTP_INSECURE_AUTH):
            logging.warning(insecure_auth_msg)
        else:
            raise ValueError(insecure_auth_msg)

    if get_config(CONF_HTTP_AUTH_MODE) != "browser":
        logging.warning(
            "CSRF protection is disabled; "
            "authenticated clients are vulnerable to CSRF attacks"
        )

    def get_policy(route: str):
        return auth_provider.get_access_policies(route)

    def _authenticate(self: HttpEngine):
        return _auth_user(self, auth_provider, sessions)

    add_method(HttpEngine, _handle_auth_st)
    add_method(HttpEngine, _handle_auth_header_st)
    add_method(HttpEngine, get_policy, "static")
    add_method(HttpEngine, _authenticate)
