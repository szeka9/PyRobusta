"""
Module for HTTP Basic Authentication.

This module overrides the auth placeholder HttpEngine._handle_auth_st(),
and applies the basic authentication scheme, with hash-based password storage,
and role-based authorization.
"""

# pylint: disable=W0212,R0401

import hashlib
import gc
import os
import binascii

from pyrobusta.protocol import http
from pyrobusta.utils.patch import add_method
from pyrobusta.utils.helpers import iterate_segments
from pyrobusta.utils.crypto import (
    constant_time_equal,
    create_signed_token,
    verify_signed_token,
)
from pyrobusta.utils.config import (
    get_config,
    CONF_PASSWD_FILE,
    CONF_ROLES_FILE,
    CONF_HTTP_AUTH,
    CONF_HTTP_AUTH_MODE,
    CONF_HTTP_INSECURE_AUTH,
    CONF_TLS,
)
from pyrobusta.utils.logging import warning

_MAX_ROLES = 32
_NO_POLICY = 2**_MAX_ROLES
_ALL_ROLES = 2**_MAX_ROLES - 1

_ROLE_INDEX = {}
_USERS = {}  # {"user": [b"<password-hash>", b"<role-mask>", b"<csrf_signing_key>"]}
_ATTR_TREE = None  # root node: /

_CSRF_NONCE_SIZE = 16
_CSRF_USER_SECRET_SIZE = 32
_DUMMY_HASH = hashlib.sha256(b"invalid-user").digest()


class AttributeNode:
    """
    Tree-based data structure for authorization.
    The tree represents predefined authorization masks defined
    for different segments of URL paths.
    """

    __slots__ = ("name", "children", "attributes")

    def __init__(self, name: str):
        self.name = name
        self.children = []
        self.attributes = None

    def add_child(self, node):
        """
        Add a child node to the current node.
        """
        self.children.append(node)

    def iter_tree(self, path: str, glob: bool = False):
        """
        Generator for iterating over the nodes of the tree
        on a predefined path.
        """
        current_node = self
        for segment in iterate_segments(path, "/"):
            segment = segment.lower()
            if not segment:
                continue
            child_node = None
            while child_node is None:
                for child in current_node.children:
                    if child.name == segment:
                        child_node = child
                        break
                if glob and child_node is None:
                    for child in current_node.children:
                        if child.name == "*":
                            child_node = child
                            break
                if child_node is None:
                    # Yield (None, segment) until the caller inserts the
                    # missing child, or handles this condition in another way.
                    # Once the child exists, resume traversal automatically.
                    yield None, segment
            yield child_node, segment
            current_node = child_node

    def insert_path(self, path: str, attributes: dict):
        """
        Introduce missing nodes in the tree based on
        a specific path with attributes defined for the
        last node corresponding to the trailing path segment.
        """
        if not path.startswith("/") or path.find("/**/") != -1:
            raise ValueError()
        current_node = self
        for iter_node, segment in self.iter_tree(path, glob=False):
            if not iter_node:
                n = AttributeNode(segment)
                current_node.add_child(n)
            else:
                current_node = iter_node
        current_node.attributes = attributes.copy()

    def get_attributes(self, path: str):
        """
        Retrieve the attributes of a node, corresponding
        to the last segment of a path. Use glob-based rules
        if nodes of trailing path segments are missing.
        - when a single path segment is missing: resolve attributes from '*' node
        - when multiple trailing path segments are missing: resolve attributes from '**' node
        """
        current_node = self

        # Calculate number of segments for globbing
        num_segments = 0
        prev = "/"
        for c in path:
            if prev == "/" and c != "/":
                num_segments += 1
            prev = c

        # Iterate nodes
        parent_glob = (
            None  # Track parent attributes corresponding to recursive globs (**)
        )
        num_nodes = 0

        for iter_node, _ in self.iter_tree(path, glob=True):
            num_nodes += 1
            glob = None

            for child in current_node.children:
                if num_nodes == num_segments and child.name == "*":
                    glob = child
                if child.name == "**":
                    parent_glob = child

            current_node = iter_node
            if not iter_node:
                break

        if not current_node:
            if glob:
                return glob.attributes
            if parent_glob:
                return parent_glob.attributes
            return
        return current_node.attributes


def index_roles(roles: str):
    """
    Create a common index for roles defined in user
    definitions and role definitions, and assign a binary
    mask to each role, used for authorization.
    """
    role_mask = 0b0
    for role in iterate_segments(roles, ","):
        role = role.strip().lower()
        if not role:
            continue
        if role not in _ROLE_INDEX and role != "*":
            if len(_ROLE_INDEX) == _MAX_ROLES:
                raise ValueError()
            _ROLE_INDEX[role] = len(_ROLE_INDEX)
        if role == "*":
            role_mask = _NO_POLICY
        else:
            role_mask |= 1 << _ROLE_INDEX[role]
    return role_mask


def _load_users():
    passwd_file = get_config(CONF_PASSWD_FILE)
    try:
        with open(passwd_file, encoding="utf-8") as users:
            for line in users:
                comment_idx = line.find("#")
                line = line[:comment_idx] if comment_idx != -1 else line
                if not line:
                    continue
                if not line.count(":") == 2:
                    raise ValueError()
                user_sep = line.find(":")
                password_sep = line.find(":", user_sep + 1)
                user = line[:user_sep].strip().lower()
                password_hash = line[user_sep + 1 : password_sep].strip()
                roles = line[password_sep + 1 :]
                role_mask = index_roles(roles)
                if not user or not password_hash:
                    raise ValueError()
                if user in _USERS:
                    raise ValueError()
                _USERS[user] = [
                    bytes.fromhex(password_hash),
                    role_mask,
                    os.urandom(_CSRF_USER_SECRET_SIZE),
                ]
    except OSError:
        warning("Unable to open: " + passwd_file)


def _load_roles():
    roles_file = get_config(CONF_ROLES_FILE)
    try:
        with open(roles_file, encoding="utf-8") as roles:
            paths = []
            attributes = {}
            for line in roles:
                comment_idx = line.find("#")
                line = line[:comment_idx].strip() if comment_idx != -1 else line.strip()

                # Parse URL path
                if line.startswith("/"):
                    if paths and attributes:
                        for path in paths:
                            _ATTR_TREE.insert_path(path, attributes)
                        paths = [line]
                        attributes = {}
                    else:
                        paths.append(line)

                # Parse attributes
                elif line:
                    if not paths:
                        raise ValueError()
                    sep = line.find(":")
                    if sep in (0, -1):
                        raise ValueError()
                    role_mask = index_roles(line[sep + 1 :])
                    for attr in iterate_segments(line[0:sep].strip(), ","):
                        attr = attr.upper()
                        if attr in attributes:
                            raise ValueError()
                        if attr:
                            attributes[attr] = role_mask
            for path in paths:
                _ATTR_TREE.insert_path(path, attributes)
    except OSError:
        warning("Unable to open: " + roles_file)


def _handle_auth_st(self, _):
    # Determine security policy
    is_public = False
    method = self.method.decode("ascii")
    url = self.url.decode("ascii")

    policy = _ATTR_TREE.get_attributes(url)
    if not policy:
        self.state = self._handle_auth_header_st
        return

    if method not in policy:
        if policy.get("*") == _NO_POLICY:
            is_public = True
    elif policy[method] == _NO_POLICY:
        is_public = True

    if is_public:
        self.state = self._route_request_st
    else:
        self.state = self._handle_auth_header_st


def _authenticate(auth_header):
    # Protocol validation
    if not auth_header or auth_header[:6].lower() != "basic ":
        return None

    # Decoding
    user_data = auth_header[6:].strip()
    try:
        user_data = binascii.a2b_base64(user_data).decode()
    except binascii.Error:
        return None

    # Authentication
    user_sep = user_data.find(":")
    if user_sep < 0:
        return None

    username = user_data[:user_sep].lower()
    user_info = _USERS.get(username)
    stored_hash = user_info[0] if user_info else _DUMMY_HASH
    password_hash = hashlib.sha256(
        user_data[user_sep + 1 :].strip().encode("ascii")
    ).digest()

    hash_ok = constant_time_equal(password_hash, stored_hash)
    user_ok = user_info is not None

    if not (user_ok and hash_ok):
        return None

    return user_info


def _is_valid_csrf_token(cookie_token, header_token, user_secret):
    if cookie_token is None or header_token is None:
        return False
    csrf_sep = header_token.find(".")
    if csrf_sep == -1:
        return False
    if cookie_token != header_token:
        return False
    if not verify_signed_token(user_secret, header_token, _CSRF_NONCE_SIZE):
        return False
    return True


def _handle_auth_header_st(self, _):
    method = self.method.decode("ascii")
    url = self.url.decode("ascii")
    auth_header = self.headers.get("authorization", "").strip()

    # Authentication
    if not (user_info := _authenticate(auth_header)):
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
                self.get_cookie("csrf-token"),
                self.headers.get("x-csrf-token"),
                user_info[2],
            ):
                self.terminate(403)
                return
        elif self.method in (self.GET, self.HEAD):
            if self.get_cookie("csrf-token") is None:
                csrf_token = create_signed_token(user_info[2], _CSRF_NONCE_SIZE)
                cookie = b"csrf-token=" + csrf_token + b"; path=/; samesite=strict"
                if get_config(CONF_TLS):
                    cookie += b"; secure"
                self.set_response_header(b"set-cookie", cookie)

    # Authorization
    policy = _ATTR_TREE.get_attributes(url)

    if not policy:
        allowed_roles = 0
    elif method not in policy:
        allowed_roles = policy.get("*", 0)
    else:
        allowed_roles = policy[method]

    if (allowed_roles & user_info[1]) == 0:
        self.terminate(403)
        return

    self.state = self._route_request_st


def apply_patches():
    """
    Apply patches to class attributes for HTTP basic authentication.
    """
    global _ATTR_TREE  # pylint: disable=W0603
    try:
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

        add_method(http.HttpEngine, _handle_auth_st)
        add_method(http.HttpEngine, _handle_auth_header_st)

        _ATTR_TREE = AttributeNode("")
        if _USERS:
            _USERS.clear()

        _load_users()
        _load_roles()
    finally:
        # Clean up temporary data structures
        _ROLE_INDEX.clear()
        gc.collect()
