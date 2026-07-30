"""
Module for HTTP Basic Authentication.

This module overrides the auth placeholder HttpEngine._handle_auth_st(),
and applies the basic authentication scheme with CSRF protection.
"""

# pylint: disable=W0212,R0401

import binascii
import os

from pyrobusta.protocol import http
from pyrobusta.utils.patch import add_method
from pyrobusta.utils.crypto import (
    constant_time_equal,
    create_signed_token,
    verify_signed_token,
    pbkdf2_sha256,
)
from pyrobusta.utils.config import (
    get_config,
    CONF_HTTP_AUTH,
    CONF_HTTP_AUTH_MODE,
    CONF_HTTP_INSECURE_AUTH,
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
from pyrobusta.utils.logging import warning

_CSRF_NONCE_SIZE = 16

_DUMMY_ITER = 5000
_DUMMY_SALT = os.urandom(16)
_DUMMY_HASH = pbkdf2_sha256(os.urandom(20), _DUMMY_SALT, _DUMMY_ITER)


def _auth_user(auth_header: str, auth_provider: IAMDatabase):
    # Protocol validation
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
        return None

    return user_info


def _is_valid_csrf_token(cookie_token: bytes, header_token: bytes, user_secret: bytes):
    if not cookie_token or not header_token:
        return False
    csrf_sep = header_token.find(b".")
    if csrf_sep == -1:
        return False
    if cookie_token != header_token:
        return False
    if not verify_signed_token(user_secret, header_token, _CSRF_NONCE_SIZE):
        return False
    return True


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
    auth_header = self.headers.get("authorization", "").strip()

    # Authentication
    if not (user_info := self._authenticate(auth_header)):
        self.set_response_header(b"WWW-Authenticate", b'Basic realm="Device"')
        self.terminate(401)
        return

    # CSRF validation, cookie setting
    if get_config(CONF_HTTP_AUTH_MODE) == "browser":
        if self.method not in (
            self.GET,
            self.HEAD,
            self.OPTIONS,
        ):
            if not _is_valid_csrf_token(
                self.get_cookie("csrf-token", "").encode("ascii"),
                self.headers.get("x-csrf-token", "").encode("ascii"),
                user_info[USER_SECRET],
            ):
                self.terminate(403)
                return
        elif self.method in (self.GET, self.HEAD):
            if self.get_cookie("csrf-token") is None:
                csrf_token = create_signed_token(
                    user_info[USER_SECRET], _CSRF_NONCE_SIZE
                )
                cookie = b"csrf-token=" + csrf_token + b"; path=/; samesite=strict"
                if get_config(CONF_TLS):
                    cookie += b"; secure"
                self.set_response_header(b"set-cookie", cookie)

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


def apply_patches(auth_provider: IAMDatabase):
    """
    Apply patches to class attributes for HTTP basic authentication.
    """
    if auth_provider is None:
        raise ValueError

    if not get_config(CONF_TLS) and get_config(CONF_HTTP_AUTH):
        insecure_auth_msg = "Authentication turned on without TLS"
        if get_config(CONF_HTTP_INSECURE_AUTH):
            warning(insecure_auth_msg)
        else:
            raise ValueError(insecure_auth_msg)

    if get_config(CONF_HTTP_AUTH_MODE) != "browser":
        warning(
            "CSRF protection is disabled; authenticated browser "
            "requests may be vulnerable to cross-site request forgery"
        )

    def get_policy(route: str):
        return auth_provider.get_access_policies(route)

    def _authenticate(auth_header: str):
        return _auth_user(auth_header, auth_provider)

    add_method(http.HttpEngine, _handle_auth_st)
    add_method(http.HttpEngine, _handle_auth_header_st)
    add_method(http.HttpEngine, get_policy, "static")
    add_method(http.HttpEngine, _authenticate, "static")
