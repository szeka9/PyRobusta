"""
Module for managing users
"""

import os
import binascii
import gc

from pyrobusta.utils.crypto import pbkdf2_sha256, validate_password
from pyrobusta.utils.lexpath import iterate_segments
from pyrobusta.utils.logging import error
from pyrobusta import PYROBUSTA_VERSION

MAX_ROLES = 32
NO_POLICY = 2**MAX_ROLES
NO_ROLES = 0b0
RUNTIME_SECRET_SIZE = 32

# Values for indexing user records
ROLE_MASK = 0
PASS_HASH = 1
PASS_SALT = 2
PASS_ITER = 3
PASS_ALGO = 4
USER_SECRET = 5


class IAMDatabase:
    """
    Identity and Access Management database for
    managing users and resources permissions.
    """

    __slots__ = (
        "_role_index",
        "_users",
        "_attribute_tree",
        "_passwd_file",
        "_roles_file",
    )

    def __init__(self, passwd_file, roles_file):
        self._role_index = {}
        self._users = {}
        # {"user": [
        #   b"<role-mask>",
        #   b"<password-hash>",
        #   b"<salt>",
        #   b"<iterations>",
        #   <password-algo>,
        #   b"<runtime-secret>"
        # ]}
        self._attribute_tree = None
        self._passwd_file = passwd_file
        self._roles_file = roles_file

    def load(
        self,
    ):
        """
        Load users and roles from configuration.
        """
        try:
            users = self._load_users()
            attribute_tree = self._load_roles()
            self._users = users
            self._attribute_tree = attribute_tree
        except OSError as e:
            error("%s: unable to open config: error=[%s]", __name__, e)
            return False
        finally:
            # Clean up temporary data structures
            self._role_index.clear()
            gc.collect()
        return True

    def _parse_user(self, user_line):
        (
            name,
            role_mask,
            pass_hash,
            salt,
            iterations,
            algo,
            _,
        ) = user_line.split(":")

        name = name.strip()
        role_mask = self.index_roles(role_mask)
        pass_hash = binascii.a2b_base64(pass_hash)
        salt = binascii.a2b_base64(salt)
        iterations = int(iterations)

        return (
            role_mask,
            pass_hash,
            salt,
            iterations,
            algo,
            os.urandom(RUNTIME_SECRET_SIZE),
        )

    def _load_users(self):
        users = {}
        with open(self._passwd_file, encoding="utf-8") as passwd_file:
            for line in passwd_file:
                name = line[: line.find(":")] if line.find(":") != -1 else ""
                comment_idx = line.find("#")
                line = line[:comment_idx].strip() if comment_idx != -1 else line.strip()
                if not line:
                    continue
                if not name:
                    raise ValueError()
                if name in users:
                    raise ValueError()
                record = self._parse_user(line)
                users[name] = record
        return users

    def _load_roles(self):
        attribute_tree = AttributeNode("")
        with open(self._roles_file, encoding="utf-8") as roles:
            paths = []
            attributes = {}
            for line in roles:
                comment_idx = line.find("#")
                line = line[:comment_idx].strip() if comment_idx != -1 else line.strip()

                # Parse URL path
                if line.startswith("/"):
                    if paths and attributes:
                        for path in paths:
                            attribute_tree.insert_path(path, attributes)
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
                    role_mask = self.index_roles(line[sep + 1 :])
                    for attr in iterate_segments(line[0:sep].strip(), ","):
                        attr = attr.upper()
                        if attr in attributes:
                            raise ValueError()
                        if attr:
                            attributes[attr] = role_mask
            for path in paths:
                attribute_tree.insert_path(path, attributes)
        return attribute_tree

    def index_roles(self, roles: str):
        """
        Create a common index for roles defined in user
        definitions and role definitions, and assign a binary
        mask to each role, used for authorization.
        """
        role_mask = NO_ROLES
        for role in iterate_segments(roles, ","):
            role = role.strip().lower()
            if not role:
                continue
            if role not in self._role_index and role != "*":
                if len(self._role_index) == MAX_ROLES:
                    raise ValueError()
                self._role_index[role] = len(self._role_index)
            if role == "*":
                role_mask = NO_POLICY
            else:
                role_mask |= 1 << self._role_index[role]
        return role_mask

    def get_user_info(self, name):
        """
        Get a user record by username.
        """
        return self._users.get(name)

    def create_user(
        self, name: str, password: str, roles: list[str], iterations: int = 5000
    ):
        """
        Create a user definition and add it to the configured passwd file.
        """
        try:
            with open(self._passwd_file, "r", encoding="utf-8") as users:
                for line in users:
                    if line.startswith(name + ":"):
                        raise ValueError("User exists")
        except OSError:
            pass

        validate_password(password)

        salt = os.urandom(16)
        derived_key = pbkdf2_sha256(
            password.encode("utf-8"),
            salt,
            iterations,
            dklen=32,
        )

        if not isinstance(roles, list):
            roles = [roles]

        with open(self._passwd_file, "a", encoding="utf-8") as users:
            users.write(
                "\n"
                + ":".join(
                    (
                        name,
                        ",".join(roles),
                        binascii.b2a_base64(derived_key, False).decode("ascii"),
                        binascii.b2a_base64(salt, False).decode("ascii"),
                        str(iterations),
                        "PBKDF2-HMAC-SHA256",
                        PYROBUSTA_VERSION,
                    )
                )
            )
        self.load()

    def get_access_policies(self, resource: str):
        """
        Get access policies associated to a resource.
        """
        return self._attribute_tree.get_attributes(resource)


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
            return None
        return current_node.attributes
