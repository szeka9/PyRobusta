import os
import base64

from http_base import TestHttpBase


class TestBasicAuthPolicyStateMachine(TestHttpBase):
    """
    Tests for HTTP basic auth policy.
    """

    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()
        cls.base_config = {
            "http_auth": "basic",
            "passwd_file": "/tmp/pyrobusta.passwd",
            "roles_file": "/tmp/pyrobusta.roles",
            # For disbaling authentication related warning messages
            "tls": True,
        }

    def test_basic_auth_public_resource(self):
        self.iam_db._attribute_tree.insert_path(
            "/app/public", {"GET": self.iam_module.NO_POLICY}
        )
        self.engine.state = self.engine._handle_auth_st
        self.engine.url = b"/app/public"
        self.engine.method = b"GET"

        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._route_request_st)

    def test_basic_auth_private_resource_exact_rule(self):
        self.iam_db._attribute_tree.insert_path("/app/private", {"GET": 0b001})
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
        cls.cwd = os.getcwd()
        cls.base_config = {
            "http_auth": "basic",
            "passwd_file": "/tmp/pyrobusta.passwd",
            "roles_file": "/tmp/pyrobusta.roles",
            # For disbaling authentication related warning messages
            "tls": True,
        }

        cls.passwd_content = (
            "# User configuration\n"
            "alice:role-1:mKmmf5wBEtlkty7LEcphieciOd3Pl0yY7r3WmDiZnzg=:XTQgg3Has79lDTNYVW+aPw=="
            ":5000:PBKDF2-HMAC-SHA256:v1.2.3\n"
            "bob:role-2:sOqLqi48jCQUiR+VpcCcfMgKcKCspbE902y0yFe0DV4=:5PzMbQQJtQRP8aZ9C7t8qQ=="
            ":5000:PBKDF2-HMAC-SHA256:v1.2.3\n"
            "charlie:role-1,role-3:mCDiXO4Uqd16CCONPWKAP5G63A/QH9WVuo5mzefgBj8="
            ":eekcG1mmHUqftsVlmHtXeA==:5000:PBKDF2-HMAC-SHA256:v1.2.3\n"
        )

        cls.roles_content = "/app/private\nGET: role-1\n"

    def prepare_request(self, auth_header=None):
        self.engine.state = self.engine._handle_auth_header_st
        self.engine.url = b"/app/private"
        self.engine.method = b"GET"
        if auth_header:
            self.engine.headers["authorization"] = auth_header

    def test_basic_auth_successful(self):
        self.prepare_request(
            auth_header="Basic "
            + base64.b64encode(
                "alice:alice's-secret-password".encode("ascii")
            ).decode(),
        )

        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._route_request_st)
        self.assertNotEqual(self.engine.status_code, 401)

    def test_basic_auth_unknown_user(self):
        self.prepare_request(
            auth_header="Basic "
            + base64.b64encode(
                "user-unknown:super-secret-password".encode("ascii")
            ).decode(),
        )

        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._terminal_st)
        self.assertEqual(self.engine.status_code, 401)

    def test_basic_auth_user_nok(self):
        self.prepare_request(
            auth_header="Basic "
            + base64.b64encode(
                "invalid:alice's-secret-password".encode("ascii")
            ).decode(),
        )

        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._terminal_st)
        self.assertEqual(self.engine.status_code, 401)

    def test_basic_auth_user_empty(self):
        self.prepare_request(
            auth_header="Basic "
            + base64.b64encode(":alice's-secret-password".encode("ascii")).decode(),
        )

        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._terminal_st)
        self.assertEqual(self.engine.status_code, 401)

    def test_basic_auth_password_nok(self):
        self.prepare_request(
            auth_header="Basic "
            + base64.b64encode("alice:invalid".encode("ascii")).decode(),
        )

        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._terminal_st)
        self.assertEqual(self.engine.status_code, 401)

    def test_basic_auth_password_empty(self):
        self.prepare_request(
            auth_header="Basic " + base64.b64encode("alice:".encode("ascii")).decode(),
        )

        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._terminal_st)
        self.assertEqual(self.engine.status_code, 401)

    def test_basic_auth_role_nok(self):
        self.prepare_request(
            auth_header="Basic "
            + base64.b64encode("bob:bob's-secret-password".encode("ascii")).decode()
        )

        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._terminal_st)
        self.assertEqual(self.engine.status_code, 403)

    def test_basic_auth_header_missing(self):
        self.prepare_request()

        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._terminal_st)
        self.assertEqual(self.engine.status_code, 401)

    def test_basic_auth_header_incomplete(self):
        self.prepare_request(auth_header="Basic ")

        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._terminal_st)
        self.assertEqual(self.engine.status_code, 401)

    def test_basic_auth_invalid_encoding(self):
        self.prepare_request(auth_header="Basic invalid-base64")

        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._terminal_st)
        self.assertEqual(self.engine.status_code, 401)

    def test_basic_auth_missing_colon(self):
        self.prepare_request(
            auth_header="Basic "
            + base64.b64encode("alicealice's-secret-password".encode("ascii")).decode(),
        )

        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._terminal_st)
        self.assertEqual(self.engine.status_code, 401)

    def test_basic_auth_multiple_colon(self):
        self.prepare_request(
            auth_header="Basic "
            + base64.b64encode(
                "charlie:charlie's-secret:password".encode("ascii")
            ).decode(),
        )

        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._route_request_st)
        self.assertNotEqual(self.engine.status_code, 401)

    def test_basic_auth_scheme_case_sensitivity(self):
        self.prepare_request(
            auth_header="bAsIc "
            + base64.b64encode(
                "alice:alice's-secret-password".encode("ascii")
            ).decode(),
        )

        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._route_request_st)
        self.assertNotEqual(self.engine.status_code, 401)

    def test_basic_auth_invalid_scheme(self):
        self.prepare_request(
            auth_header="Bearer "
            + base64.b64encode(
                "alice:alice's-secret-password".encode("ascii")
            ).decode(),
        )
        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._terminal_st)
        self.assertEqual(self.engine.status_code, 401)


class TestBasicAuthCSRFStateMachine(TestHttpBase):
    """
    Tests for HTTP authentication with CSRF protection.
    """

    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()
        cls.base_config = {
            "http_auth": "basic",
            "passwd_file": "/tmp/pyrobusta.passwd",
            "roles_file": "/tmp/pyrobusta.roles",
            # For disbaling authentication related warning messages
            "tls": True,
        }

        cls.passwd_content = (
            "# User configuration\n"
            "alice:role-1:mKmmf5wBEtlkty7LEcphieciOd3Pl0yY7r3WmDiZnzg=:XTQgg3Has79lDTNYVW+aPw=="
            ":5000:PBKDF2-HMAC-SHA256:v1.2.3\n"
        )

        cls.roles_content = "/app/private\nGET: role-1\nPOST: role-1\n"

    def prepare_request(self, auth_header=None):
        self.engine.state = self.engine._handle_auth_header_st
        self.engine.url = b"/app/private"
        self.engine.method = b"GET"
        if auth_header:
            self.engine.headers["authorization"] = auth_header

    def test_csrf_generated_token_valid(self):
        self.prepare_request(
            auth_header="Basic "
            + base64.b64encode("alice:alice's-secret-password".encode("ascii")).decode()
        )
        self.engine.method = b"GET"

        self.engine.state(self.rx)

        user_secret = self.iam_db.get_user_info("alice")[-1]
        cookie_name, csrf_token = (
            self.engine._lookup(self.engine.resp_headers, b"set-cookie")
            .split(b";")[0]
            .split(b"=")
        )
        is_token_valid = self.crypto_module.verify_signed_token(
            user_secret, csrf_token, self.basic_auth_module._CSRF_NONCE_SIZE
        )

        self.assertEqual(cookie_name, b"csrf-token")
        self.assertTrue(is_token_valid)
        self.assertEqual(self.engine.state, self.engine._route_request_st)
        self.assertEqual(self.engine.status_code, None)

    def test_csrf_existing_token_accepted(self):
        self.prepare_request(
            auth_header="Basic "
            + base64.b64encode("alice:alice's-secret-password".encode("ascii")).decode()
        )
        self.engine.method = b"GET"

        user_secret = self.iam_db.get_user_info("alice")[-1]
        csrf_token = self.crypto_module.create_signed_token(
            user_secret, self.basic_auth_module._CSRF_NONCE_SIZE
        )
        self.engine.headers["cookie"] = "csrf-token=" + csrf_token.decode("ascii")
        self.engine.headers["x-csrf-token"] = csrf_token.decode("ascii")

        self.engine.state(self.rx)

        with self.assertRaises(ValueError):
            self.engine._lookup(self.engine.resp_headers, b"set-cookie")

        self.assertEqual(self.engine.state, self.engine._route_request_st)
        self.assertEqual(self.engine.status_code, None)

    def test_csrf_request_token_accepted(self):
        self.prepare_request(
            auth_header="Basic "
            + base64.b64encode("alice:alice's-secret-password".encode("ascii")).decode()
        )
        self.engine.method = b"POST"

        user_secret = self.iam_db.get_user_info("alice")[-1]
        csrf_token = self.crypto_module.create_signed_token(
            user_secret, self.basic_auth_module._CSRF_NONCE_SIZE
        )
        self.engine.headers["cookie"] = "csrf-token=" + csrf_token.decode("ascii")
        self.engine.headers["x-csrf-token"] = csrf_token.decode("ascii")

        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._route_request_st)
        self.assertEqual(self.engine.status_code, None)

    def test_csrf_request_forged_token_rejected(self):
        self.prepare_request(
            auth_header="Basic "
            + base64.b64encode("alice:alice's-secret-password".encode("ascii")).decode()
        )
        self.engine.method = b"POST"

        forged_user_secret = os.urandom(self.basic_auth_module._CSRF_NONCE_SIZE)
        csrf_token = self.crypto_module.create_signed_token(
            forged_user_secret, self.basic_auth_module._CSRF_NONCE_SIZE
        )
        self.engine.headers["cookie"] = "csrf-token=" + csrf_token.decode("ascii")
        self.engine.headers["x-csrf-token"] = csrf_token.decode("ascii")

        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._terminal_st)
        self.assertEqual(self.engine.status_code, 403)

    def test_csrf_request_missing_csrf_rejected(self):
        self.prepare_request(
            auth_header="Basic "
            + base64.b64encode("alice:alice's-secret-password".encode("ascii")).decode()
        )
        self.engine.method = b"POST"

        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._terminal_st)
        self.assertEqual(self.engine.status_code, 403)

    def test_csrf_missing_cookie_rejected(self):
        self.prepare_request(
            auth_header="Basic "
            + base64.b64encode("alice:alice's-secret-password".encode("ascii")).decode()
        )
        self.engine.method = b"POST"

        user_secret = self.iam_db.get_user_info("alice")[-1]
        csrf_token = self.crypto_module.create_signed_token(
            user_secret, self.basic_auth_module._CSRF_NONCE_SIZE
        )
        self.engine.headers["x-csrf-token"] = csrf_token.decode("ascii")

        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._terminal_st)
        self.assertEqual(self.engine.status_code, 403)

    def test_csrf_missing_token_rejected(self):
        self.prepare_request(
            auth_header="Basic "
            + base64.b64encode("alice:alice's-secret-password".encode("ascii")).decode()
        )
        self.engine.method = b"POST"

        user_secret = self.iam_db.get_user_info("alice")[-1]
        csrf_token = self.crypto_module.create_signed_token(
            user_secret, self.basic_auth_module._CSRF_NONCE_SIZE
        )
        self.engine.headers["cookie"] = "csrf-token=" + csrf_token.decode("ascii")

        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._terminal_st)
        self.assertEqual(self.engine.status_code, 403)
