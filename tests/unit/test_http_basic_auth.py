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
            "http_session": "false",
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
            "http_session": "false",
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
        csrf_key = self.crypto_module.HmacSha256(user_secret)
        csrf_secret = csrf_key.digest(self.csrf_module._CSRF_INFO)
        cookie_name, csrf_token = (
            self.engine._lookup(self.engine.resp_headers, b"set-cookie")
            .split(b";")[0]
            .split(b"=")
        )
        is_token_valid = self.crypto_module.verify_signed_token(
            csrf_secret, csrf_token, self.csrf_module._NONCE_SIZE
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
            user_secret, os.urandom(self.csrf_module._NONCE_SIZE)
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
        csrf_key = self.crypto_module.HmacSha256(user_secret)
        csrf_secret = csrf_key.digest(self.csrf_module._CSRF_INFO)
        csrf_token = self.crypto_module.create_signed_token(
            csrf_secret, os.urandom(self.csrf_module._NONCE_SIZE)
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

        forged_user_secret = os.urandom(self.csrf_module._NONCE_SIZE)
        csrf_token = self.crypto_module.create_signed_token(
            forged_user_secret, os.urandom(self.csrf_module._NONCE_SIZE)
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
            user_secret, os.urandom(self.csrf_module._NONCE_SIZE)
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
            user_secret, os.urandom(self.csrf_module._NONCE_SIZE)
        )
        self.engine.headers["cookie"] = "csrf-token=" + csrf_token.decode("ascii")

        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._terminal_st)
        self.assertEqual(self.engine.status_code, 403)


class TestBasicAuthSessionStateMachine(TestHttpBase):
    """
    Tests for HTTP authentication with session management.
    """

    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()
        cls.base_config = {
            "http_auth": "basic",
            "http_auth_mode": "api",  # Disabling CSRF for session tests
            "http_sessions": "true",
            "http_session_ttl_sec": 5,
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

    def get_cookie_data(self, cookie_name):
        try:
            cookie_header = self.engine._lookup(self.engine.resp_headers, b"set-cookie")
        except ValueError:
            return None
        cookies = cookie_header.split(b";")
        for cookie in cookies:
            name, _, value = cookie.partition(b"=")
            if name.strip() == cookie_name.encode("ascii"):
                return value.strip()
        return None

    def create_session_cookie(self, username, ttl=None):
        user_secret = self.iam_db.get_user_info(username)[-1]
        session_cookie = self.session_module.create_cookie(
            username,
            user_secret,
            ttl if ttl is not None else self.base_config["http_session_ttl_sec"],
        )
        return session_cookie.split(b";")[0].split(b"=")[1]

    def test_session_generated_cookie_valid(self):
        self.prepare_request(
            auth_header="Basic "
            + base64.b64encode("alice:alice's-secret-password".encode("ascii")).decode()
        )
        self.engine.method = b"GET"

        self.engine.state(self.rx)

        session_cookie = self.get_cookie_data("session")
        credentials = self.session_module.verify_cookie(session_cookie, self.iam_db)

        self.assertNotEqual(credentials, None)
        self.assertEqual(self.engine.state, self.engine._route_request_st)
        self.assertEqual(self.engine.status_code, None)

    def test_session_existing_cookie_accepted(self):
        self.prepare_request(auth_header="")
        self.engine.method = b"GET"

        session_cookie = self.create_session_cookie("alice")
        self.engine.headers["cookie"] = "session=" + session_cookie.decode("ascii")
        self.engine.state(self.rx)

        self.assertEqual(self.get_cookie_data("session"), None)
        self.assertEqual(self.engine.state, self.engine._route_request_st)

    def test_session_expired_cookie_rejected(self):
        self.prepare_request(auth_header="")
        self.engine.method = b"GET"

        session_cookie = self.create_session_cookie("alice", ttl=0)
        self.engine.headers["cookie"] = "session=" + session_cookie.decode("ascii")
        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._terminal_st)
        self.assertEqual(self.engine.status_code, 401)

    def test_session_invalid_cookie_rejected(self):
        self.prepare_request(auth_header="")
        self.engine.method = b"GET"

        # Create a valid session cookie and then tamper with it
        session_cookie = self.create_session_cookie("alice")
        invalid_digit = b"0" if session_cookie[-1:] != b"0" else b"1"
        tampered_session_cookie = (
            session_cookie[:-1] + invalid_digit
        )  # Tamper with the last character
        self.engine.headers["cookie"] = "session=" + tampered_session_cookie.decode(
            "ascii"
        )
        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._terminal_st)
        self.assertEqual(self.engine.status_code, 401)

    def test_session_missing_cookie_rejected(self):
        self.prepare_request(auth_header="")
        self.engine.method = b"GET"

        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._terminal_st)
        self.assertEqual(self.engine.status_code, 401)

    def test_session_invalid_user_rejected(self):
        self.prepare_request(auth_header="")
        self.engine.method = b"GET"

        # Create a valid session cookie for a non-existent user
        fake_user_secret = os.urandom(self.iam_module.RUNTIME_SECRET_SIZE)
        session_cookie = (
            self.session_module.create_cookie(
                "nonexistentuser",
                fake_user_secret,
                self.base_config["http_session_ttl_sec"],
            )
            .split(b";")[0]
            .split(b"=")[1]
        )
        self.engine.headers["cookie"] = "session=" + session_cookie.decode("ascii")
        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._terminal_st)
        self.assertEqual(self.engine.status_code, 401)

    def test_expired_cookie_with_auth_header_generates_new_session(self):
        self.prepare_request(
            auth_header="Basic "
            + base64.b64encode("alice:alice's-secret-password".encode("ascii")).decode()
        )
        self.engine.method = b"GET"

        # Create an expired session cookie
        expired_session_cookie = self.create_session_cookie("alice", ttl=0)
        self.engine.headers["cookie"] = "session=" + expired_session_cookie.decode(
            "ascii"
        )
        self.engine.state(self.rx)

        session_cookie = self.get_cookie_data("session")
        credentials = self.session_module.verify_cookie(session_cookie, self.iam_db)

        self.assertNotEqual(credentials, None)
        self.assertNotEqual(session_cookie, expired_session_cookie)
        self.assertEqual(self.engine.state, self.engine._route_request_st)
        self.assertEqual(self.engine.status_code, None)

    def test_valid_cookie_with_auth_header_does_not_generate_new_session(self):
        self.prepare_request(
            auth_header="Basic "
            + base64.b64encode("alice:alice's-secret-password".encode("ascii")).decode()
        )
        self.engine.method = b"GET"
        session_cookie = self.create_session_cookie("alice")
        self.engine.headers["cookie"] = "session=" + session_cookie.decode("ascii")
        self.engine.state(self.rx)

        self.assertEqual(self.get_cookie_data("session"), None)
        self.assertEqual(self.engine.state, self.engine._route_request_st)
        self.assertEqual(self.engine.status_code, None)
