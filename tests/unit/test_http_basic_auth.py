import os
import unittest
import hashlib
import base64
import tempfile

from http_base import TestHttpBase


class TestBasicAuthPolicyStateMachine(TestHttpBase):
    """
    Tests for HTTP basic auth policy.
    """

    @classmethod
    def setUpClass(cls):
        cls.base_config = {"http_auth": "basic"}
        cls.cwd = os.getcwd()

    def test_basic_auth_public_resource(self):
        self.basic_auth_module._ATTR_TREE.insert_path(
            "/app/public", {"GET": self.basic_auth_module._NO_POLICY}
        )
        self.engine.state = self.engine._handle_auth_st
        self.engine.url = b"/app/public"
        self.engine.method = b"GET"

        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._route_request_st)

    def test_basic_auth_private_resource_exact_rule(self):
        self.basic_auth_module._ATTR_TREE.insert_path("/app/private", {"GET": 0b001})
        self.engine.state = self.engine._handle_auth_st
        self.engine.url = b"/app/private"
        self.engine.method = b"GET"

        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._handle_auth_header_st)

    def test_basic_auth_private_resource_no_rule(self):
        self.engine.state = self.engine._handle_auth_st
        self.engine.url = b"/app/public"
        self.engine.method = b"GET"

        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._handle_auth_header_st)


class TestBasicAuthStateMachine(TestHttpBase):
    """
    Tests for HTTP authentication & authorization.
    """

    @classmethod
    def setUpClass(cls):
        cls.base_config = {"http_auth": "basic"}
        cls.cwd = os.getcwd()

    def prepare_auth(self, user, password, auth_header, user_roles, route_roles):
        if user is not None and password is not None:
            password_hash = hashlib.sha256(password.encode()).digest()
            self.basic_auth_module._USERS[user] = [password_hash, user_roles]

        self.basic_auth_module._ATTR_TREE.insert_path(
            "/app/private", {"GET": route_roles}
        )
        self.engine.state = self.engine._handle_auth_header_st
        self.engine.url = b"/app/private"
        self.engine.method = b"GET"
        if auth_header:
            self.engine.headers["authorization"] = auth_header

    def test_basic_auth_successful(self):
        self.prepare_auth(
            user="dummy-user",
            password="<password of dummy user>",
            auth_header="Basic "
            + base64.b64encode(
                "dummy-user:<password of dummy user>".encode("ascii")
            ).decode(),
            user_roles=0b001,
            route_roles=0b001,
        )

        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._route_request_st)
        self.assertNotEqual(self.engine.status_code, 401)

    def test_basic_auth_unknown_user(self):
        self.prepare_auth(
            user=None,
            password=None,
            auth_header="Basic "
            + base64.b64encode(
                "dummy-user:<password of dummy user>".encode("ascii")
            ).decode(),
            user_roles=0b001,
            route_roles=0b001,
        )

        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._terminal_st)
        self.assertEqual(self.engine.status_code, 401)

    def test_basic_auth_user_nok(self):
        self.prepare_auth(
            user="dummy-user",
            password="<password of dummy user>",
            auth_header="Basic "
            + base64.b64encode(
                "invalid:<password of dummy user>".encode("ascii")
            ).decode(),
            user_roles=0b001,
            route_roles=0b001,
        )

        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._terminal_st)
        self.assertEqual(self.engine.status_code, 401)

    def test_basic_auth_user_empty(self):
        self.prepare_auth(
            user="dummy-user",
            password="<password of dummy user>",
            auth_header="Basic "
            + base64.b64encode(":<password of dummy user>".encode("ascii")).decode(),
            user_roles=0b001,
            route_roles=0b001,
        )

        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._terminal_st)
        self.assertEqual(self.engine.status_code, 401)

    def test_basic_auth_password_nok(self):
        self.prepare_auth(
            user="dummy-user",
            password="<password of dummy user>",
            auth_header="Basic "
            + base64.b64encode("dummy-user:invalid".encode("ascii")).decode(),
            user_roles=0b001,
            route_roles=0b001,
        )

        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._terminal_st)
        self.assertEqual(self.engine.status_code, 401)

    def test_basic_auth_password_empty(self):
        self.prepare_auth(
            user="dummy-user",
            password="<password of dummy user>",
            auth_header="Basic "
            + base64.b64encode("dummy-user:".encode("ascii")).decode(),
            user_roles=0b001,
            route_roles=0b001,
        )

        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._terminal_st)
        self.assertEqual(self.engine.status_code, 401)

    def test_basic_auth_role_nok(self):
        self.prepare_auth(
            user="dummy-user",
            password="<password of dummy user>",
            auth_header="Basic "
            + base64.b64encode(
                "dummy-user:<password of dummy user>".encode("ascii")
            ).decode(),
            user_roles=0b010,
            route_roles=0b001,
        )

        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._terminal_st)
        self.assertEqual(self.engine.status_code, 403)

    def test_basic_auth_header_missing(self):
        self.prepare_auth(
            user="dummy-user",
            password="<password of dummy user>",
            auth_header="",
            user_roles=0b001,
            route_roles=0b001,
        )

        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._terminal_st)
        self.assertEqual(self.engine.status_code, 401)

    def test_basic_auth_header_incomplete(self):
        self.prepare_auth(
            user="dummy-user",
            password="<password of dummy user>",
            auth_header="Basic ",
            user_roles=0b001,
            route_roles=0b001,
        )

        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._terminal_st)
        self.assertEqual(self.engine.status_code, 401)

    def test_basic_auth_invalid_encoding(self):
        self.prepare_auth(
            user="dummy-user",
            password="<password of dummy user>",
            auth_header="Basic invalid-base64",
            user_roles=0b001,
            route_roles=0b001,
        )

        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._terminal_st)
        self.assertEqual(self.engine.status_code, 401)

    def test_basic_auth_missing_colon(self):
        self.prepare_auth(
            user="dummy-user",
            password="<password of dummy user>",
            auth_header="Basic "
            + base64.b64encode(
                "dummy-user<password of dummy user>".encode("ascii")
            ).decode(),
            user_roles=0b001,
            route_roles=0b001,
        )

        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._terminal_st)
        self.assertEqual(self.engine.status_code, 401)

    def test_basic_auth_multiple_colon(self):
        self.prepare_auth(
            user="dummy-user",
            password="dummy:password",
            auth_header="Basic "
            + base64.b64encode("dummy-user:dummy:password".encode("ascii")).decode(),
            user_roles=0b001,
            route_roles=0b001,
        )

        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._route_request_st)
        self.assertNotEqual(self.engine.status_code, 401)

    def test_basic_auth_scheme_case_sensitivity(self):
        self.prepare_auth(
            user="dummy-user",
            password="<password of dummy user>",
            auth_header="bAsIc "
            + base64.b64encode(
                "dummy-user:<password of dummy user>".encode("ascii")
            ).decode(),
            user_roles=0b001,
            route_roles=0b001,
        )

        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._route_request_st)
        self.assertNotEqual(self.engine.status_code, 401)

    def test_basic_auth_invalid_scheme(self):
        self.prepare_auth(
            user="dummy-user",
            password="<password of dummy user>",
            auth_header="Bearer "
            + base64.b64encode(
                "dummy-user:<password of dummy user>".encode("ascii")
            ).decode(),
            user_roles=0b001,
            route_roles=0b001,
        )

        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._terminal_st)
        self.assertEqual(self.engine.status_code, 401)


class TestBasicAuthPrefixTree(TestHttpBase):
    """
    Tests for authorization based on prefix tree.
    """

    @classmethod
    def setUpClass(cls):
        cls.base_config = {"http_auth": "basic"}
        cls.cwd = os.getcwd()

    def setup_roles(self, roles: dict):
        self.attr_tree = self.basic_auth_module.AttributeNode("")
        for path, attributes in roles.items():
            self.attr_tree.insert_path(path, attributes)

    def test_attribute_retrieval_exact_match(self):
        self.setup_roles({"/app/resource": {"GET": 0b001}})

        attributes = self.attr_tree.get_attributes("/app/resource")
        self.assertEqual(attributes, {"GET": 0b001})

        attributes = self.attr_tree.get_attributes("/app/resource/")
        self.assertEqual(attributes, {"GET": 0b001})

    def test_attribute_retrieval_trailing_glob(self):
        self.setup_roles({"/app/resource/*": {"GET": 0b001}})

        attributes = self.attr_tree.get_attributes("/app/resource")
        self.assertEqual(attributes, None)

        attributes = self.attr_tree.get_attributes("/app/resource/")
        self.assertEqual(attributes, None)

        attributes = self.attr_tree.get_attributes("/app/resource/name")
        self.assertEqual(attributes, {"GET": 0b001})

        attributes = self.attr_tree.get_attributes("/app/resource/name/")
        self.assertEqual(attributes, {"GET": 0b001})

        attributes = self.attr_tree.get_attributes("/app/resource/name/details")
        self.assertEqual(attributes, None)

        attributes = self.attr_tree.get_attributes("/app/resource/name/details/")
        self.assertEqual(attributes, None)

    def test_attribute_retrieval_intermediate_glob(self):
        self.setup_roles({"/app/resource/*/details": {"GET": 0b001}})

        attributes = self.attr_tree.get_attributes("/app/resource")
        self.assertEqual(attributes, None)

        attributes = self.attr_tree.get_attributes("/app/resource/")
        self.assertEqual(attributes, None)

        attributes = self.attr_tree.get_attributes("/app/resource/name")
        self.assertEqual(attributes, None)

        attributes = self.attr_tree.get_attributes("/app/resource/name/")
        self.assertEqual(attributes, None)

        attributes = self.attr_tree.get_attributes("/app/resource/name/details")
        self.assertEqual(attributes, {"GET": 0b001})

        attributes = self.attr_tree.get_attributes("/app/resource/name/details/")
        self.assertEqual(attributes, {"GET": 0b001})

    def test_attribute_retrieval_trailing_recursive_glob(self):
        self.setup_roles(
            {
                "/app/resource/**": {"GET": 0b001},
            }
        )

        attributes = self.attr_tree.get_attributes("/app/resource")
        self.assertEqual(attributes, None)

        attributes = self.attr_tree.get_attributes("/app/resource/")
        self.assertEqual(attributes, None)

        attributes = self.attr_tree.get_attributes("/app/resource/name")
        self.assertEqual(attributes, {"GET": 0b001})

        attributes = self.attr_tree.get_attributes("/app/resource/name/")
        self.assertEqual(attributes, {"GET": 0b001})

        attributes = self.attr_tree.get_attributes("/app/resource/name/details")
        self.assertEqual(attributes, {"GET": 0b001})

    def test_attribute_retrieval_glob_precedence(self):
        self.setup_roles(
            {
                "/**": {"GET": 0},
                "/app": {"GET": 1},
                "/app/*": {"GET": 2},
                "/app/**": {"GET": 3},
                "/app/*/logs": {"GET": 4},
                "/app/faults/logs": {"GET": 5},
                "/app/endpoint": {"GET": 6},
                "/app/endpoint/*": {"GET": 7},
                "/app/endpoint/**": {"GET": 8},
                "/app/endpoint/*/logs": {"GET": 9},
                "/app/endpoint/runtime/logs": {"GET": 10},
            }
        )
        attributes = self.attr_tree.get_attributes("/system/runtime/logs")
        self.assertEqual(attributes, {"GET": 0})

        attributes = self.attr_tree.get_attributes("/app")
        self.assertEqual(attributes, {"GET": 1})

        attributes = self.attr_tree.get_attributes("/app/api")
        self.assertEqual(attributes, {"GET": 2})

        attributes = self.attr_tree.get_attributes("/app/admin/status")
        self.assertEqual(attributes, {"GET": 3})

        attributes = self.attr_tree.get_attributes("/app/admin/logs")
        self.assertEqual(attributes, {"GET": 4})

        attributes = self.attr_tree.get_attributes("/app/faults/logs")
        self.assertEqual(attributes, {"GET": 5})

        attributes = self.attr_tree.get_attributes("/app/endpoint")
        self.assertEqual(attributes, {"GET": 6})

        attributes = self.attr_tree.get_attributes("/app/endpoint/status")
        self.assertEqual(attributes, {"GET": 7})

        attributes = self.attr_tree.get_attributes("/app/endpoint/resource/details")
        self.assertEqual(attributes, {"GET": 8})

        attributes = self.attr_tree.get_attributes("/app/endpoint/resource/logs")
        self.assertEqual(attributes, {"GET": 9})

        attributes = self.attr_tree.get_attributes("/app/endpoint/runtime/logs")
        self.assertEqual(attributes, {"GET": 10})


class TestBasicAuthUserConfigReader(TestHttpBase):
    """
    Tests for user configuration reader.
    """

    @classmethod
    def setUpClass(cls):
        cls.base_config = {"http_auth": "basic"}
        cls.cwd = os.getcwd()

    def test_user_reader_valid_config(self):
        file_content = (
            "# User configuration\n"
            "user-1:70b0577b18482fd0e42b92ba9a1ce90ac3b976648aa68fb8484098f76f816145:\n"
            "user-2:718a8ca4dd4d30b8dc0756ad9d7de727079869b215b03782279e372ab6911ecf:role1\n"
            "user-3:280b73d2ac8375035501e5c06acb4b770e74ec95f479e6e2643227d7f57ce7ad:role1,role2\n"
        )

        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=self.cwd
        ) as file:
            self.basic_auth_module._USERS.clear()
            file.write(file_content)
            file.flush()
            self.basic_auth_module._load_users(file.name)

        self.assertDictEqual(
            self.basic_auth_module._USERS,
            {
                "user-1": [
                    bytes.fromhex(
                        "70b0577b18482fd0e42b92ba9a1ce90ac3b976648aa68fb8484098f76f816145"
                    ),
                    0b00,
                ],
                "user-2": [
                    bytes.fromhex(
                        "718a8ca4dd4d30b8dc0756ad9d7de727079869b215b03782279e372ab6911ecf"
                    ),
                    0b01,
                ],
                "user-3": [
                    bytes.fromhex(
                        "280b73d2ac8375035501e5c06acb4b770e74ec95f479e6e2643227d7f57ce7ad"
                    ),
                    0b11,
                ],
            },
        )

    def test_user_reader_empty_user(self):
        file_content = (
            ":70b0577b18482fd0e42b92ba9a1ce90ac3b976648aa68fb8484098f76f816145:\n"
        )

        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=self.cwd
        ) as file:
            file.write(file_content)
            file.flush()
            with self.assertRaises(ValueError):
                self.basic_auth_module._load_users(file.name)

    def test_user_reader_duplicate_user(self):
        file_content = (
            "user-1:70b0577b18482fd0e42b92ba9a1ce90ac3b976648aa68fb8484098f76f816145:\n"
            "user-1:718a8ca4dd4d30b8dc0756ad9d7de727079869b215b03782279e372ab6911ecf:\n"
        )

        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=self.cwd
        ) as file:
            file.write(file_content)
            file.flush()
            with self.assertRaises(ValueError):
                self.basic_auth_module._load_users(file.name)

    def test_user_reader_empty_password(self):
        file_content = "user-1::\n"

        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=self.cwd
        ) as file:
            file.write(file_content)
            file.flush()
            with self.assertRaises(ValueError):
                self.basic_auth_module._load_users(file.name)


class TestBasicAuthRoleConfigReader(TestHttpBase):
    """
    Tests for role configuration reader.
    """

    @classmethod
    def setUpClass(cls):
        cls.base_config = {"http_auth": "basic"}
        cls.cwd = os.getcwd()

    def test_role_reader_valid_config(self):
        file_content = (
            "/*\n"
            "   *:*\n"
            "# Comment\n"
            "/app/resource\n"
            "/app/resource/* # inline comment\n"
            "    GET: role_1\n"
            "    POST,PUT:role_2,role_3\n"
            "    OPTIONS: *# inline comment\n"
            "    DELETE:\n"
            "    \n"
            " /app/api\n\n"
            "GET: role_4 \n\n"
            "POST , PUT : role_1 , role_2 "
        )

        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=self.cwd
        ) as file:
            self.basic_auth_module._ATTR_TREE = self.basic_auth_module.AttributeNode("")
            file.write(file_content)
            file.flush()
            self.basic_auth_module._load_roles(file.name)

        attributes = self.basic_auth_module._ATTR_TREE.get_attributes("/index.html")
        self.assertEqual(attributes, {"*": self.basic_auth_module._NO_POLICY})

        attributes = self.basic_auth_module._ATTR_TREE.get_attributes("/app/resource")
        self.assertEqual(
            attributes,
            {
                "GET": 0b001,
                "POST": 0b110,
                "PUT": 0b110,
                "DELETE": 0b000,
                "OPTIONS": self.basic_auth_module._NO_POLICY,
            },
        )

        attributes = self.basic_auth_module._ATTR_TREE.get_attributes("/app/api")
        self.assertEqual(
            attributes,
            {
                "GET": 0b1000,
                "POST": 0b0011,
                "PUT": 0b0011,
            },
        )

    def test_role_reader_missing_path(self):
        file_content = "   *:*\n"

        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=self.cwd
        ) as file:
            self.basic_auth_module._ATTR_TREE = self.basic_auth_module.AttributeNode("")
            file.write(file_content)
            file.flush()
            with self.assertRaises(ValueError):
                self.basic_auth_module._load_roles(file.name)

    def test_role_reader_duplicate_attribute(self):
        file_content = "/app/resource\n" + "    GET: role_1\n" + "    GET: role_2\n"

        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=self.cwd
        ) as file:
            self.basic_auth_module._ATTR_TREE = self.basic_auth_module.AttributeNode("")
            file.write(file_content)
            file.flush()
            with self.assertRaises(ValueError):
                self.basic_auth_module._load_roles(file.name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
