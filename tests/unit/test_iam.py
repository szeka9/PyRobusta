import os
import unittest
import binascii

from pyrobusta.utils.iam import AttributeNode, IAMDatabase, NO_POLICY


class TestPrefixTree(unittest.TestCase):
    """
    Tests for authorization based on prefix tree.
    """

    def setup_roles(self, roles: dict):
        self.attr_tree = AttributeNode("")
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


class TestUserConfigReader(unittest.TestCase):
    """
    Tests for user configuration reader.
    """

    def setUp(self):
        cwd = os.getcwd()
        if "tmp" not in os.listdir(cwd):
            os.mkdir(cwd + "/tmp")

        self.passwd_file = cwd + "/tmp/pyrobusta.passwd"
        self.roles_file = cwd + "/tmp/pyrobusta.roles"

        with open(self.passwd_file, "w", encoding="utf-8"):
            pass

        with open(self.roles_file, "w", encoding="utf-8"):
            pass

        self.iam_db = IAMDatabase(self.passwd_file, self.roles_file)

    def tearDown(self):
        try:
            os.remove(self.passwd_file)
            os.remove(self.roles_file)
        finally:
            super().tearDown()

    def test_user_reader_valid_config(self):
        file_content = (
            "# User configuration\n"
            "alice::mKmmf5wBEtlkty7LEcphieciOd3Pl0yY7r3WmDiZnzg=:XTQgg3Has79lDTNYVW+aPw=="
            ":5000:PBKDF2-HMAC-SHA256:v1.2.3\n"
            "bob:role-1:sOqLqi48jCQUiR+VpcCcfMgKcKCspbE902y0yFe0DV4=:5PzMbQQJtQRP8aZ9C7t8qQ=="
            ":5000:PBKDF2-HMAC-SHA256:v1.2.3\n"
            "charlie:role-1,role-2:mCDiXO4Uqd16CCONPWKAP5G63A/QH9WVuo5mzefgBj8="
            ":eekcG1mmHUqftsVlmHtXeA==:5000:PBKDF2-HMAC-SHA256:v1.2.3\n"
        )

        with open(self.passwd_file, "w", encoding="utf-8") as passwd:
            passwd.write(file_content)

        self.iam_db.load()

        self.assertDictEqual(
            self.iam_db._users,
            {
                "alice": (
                    0b00,
                    binascii.a2b_base64("mKmmf5wBEtlkty7LEcphieciOd3Pl0yY7r3WmDiZnzg="),
                    binascii.a2b_base64("XTQgg3Has79lDTNYVW+aPw=="),
                    5000,
                    "PBKDF2-HMAC-SHA256",
                    self.iam_db._users["alice"][5],  # Runtime secret
                ),
                "bob": (
                    0b01,
                    binascii.a2b_base64("sOqLqi48jCQUiR+VpcCcfMgKcKCspbE902y0yFe0DV4="),
                    binascii.a2b_base64("5PzMbQQJtQRP8aZ9C7t8qQ=="),
                    5000,
                    "PBKDF2-HMAC-SHA256",
                    self.iam_db._users["bob"][5],  # Runtime secret
                ),
                "charlie": (
                    0b11,
                    binascii.a2b_base64("mCDiXO4Uqd16CCONPWKAP5G63A/QH9WVuo5mzefgBj8="),
                    binascii.a2b_base64("eekcG1mmHUqftsVlmHtXeA=="),
                    5000,
                    "PBKDF2-HMAC-SHA256",
                    self.iam_db._users["charlie"][5],  # Runtime secret
                ),
            },
        )

    def test_user_reader_empty_user(self):
        file_content = (
            "::mKmmf5wBEtlkty7LEcphieciOd3Pl0yY7r3WmDiZnzg=:XTQgg3Has79lDTNYVW+aPw=="
            ":5000:PBKDF2-HMAC-SHA256:v1.2.3\n"
        )

        with open(self.passwd_file, "w", encoding="utf-8") as passwd:
            passwd.write(file_content)

        with self.assertRaises(ValueError):
            self.iam_db.load()

    def test_user_reader_duplicate_user(self):
        file_content = (
            "alice::mKmmf5wBEtlkty7LEcphieciOd3Pl0yY7r3WmDiZnzg=:XTQgg3Has79lDTNYVW+aPw=="
            ":5000:PBKDF2-HMAC-SHA256:v1.2.3\n"
            "alice::mKmmf5wBEtlkty7LEcphieciOd3Pl0yY7r3WmDiZnzg=:XTQgg3Has79lDTNYVW+aPw=="
            ":5000:PBKDF2-HMAC-SHA256:v1.2.3\n"
        )

        with open(self.passwd_file, "w", encoding="utf-8") as passwd:
            passwd.write(file_content)

        with self.assertRaises(ValueError):
            self.iam_db.load()

    def test_user_reader_empty_password(self):
        file_content = "alice::\n"

        with open(self.passwd_file, "w", encoding="utf-8") as passwd:
            passwd.write(file_content)

        with self.assertRaises(ValueError):
            self.iam_db.load()


class TestRoleConfigReader(unittest.TestCase):
    """
    Tests for role configuration reader.
    """

    def setUp(self):
        cwd = os.getcwd()
        if "tmp" not in os.listdir(cwd):
            os.mkdir(cwd + "/tmp")

        self.passwd_file = cwd + "/tmp/pyrobusta.passwd"
        self.roles_file = cwd + "/tmp/pyrobusta.roles"

        with open(self.passwd_file, "w", encoding="utf-8"):
            pass

        with open(self.roles_file, "w", encoding="utf-8"):
            pass

        self.iam_db = IAMDatabase(self.passwd_file, self.roles_file)

    def tearDown(self):
        try:
            os.remove(self.passwd_file)
            os.remove(self.roles_file)
        finally:
            super().tearDown()

    def test_role_reader_valid_config(self):
        file_content = (
            "/*\n"
            "   *:*\n"
            "# Comment\n"
            "/app/resource\n"
            "/app/resource/* # inline comment\n"
            "    GET: role_1\n"
            "    pOsT,PuT:role_2,role_3\n"
            "    OPTIONS: *# inline comment\n"
            "    DELETE:\n"
            "    \n"
            " /app/api\n\n"
            "GET: role_4 \n\n"
            "POST , PUT : role_1 , role_2 "
        )

        with open(self.roles_file, "w", encoding="utf-8") as roles:
            self.iam_db._attribute_tree = AttributeNode("")
            roles.write(file_content)

        self.iam_db.load()

        attributes = self.iam_db.get_access_policies("/index.html")
        self.assertEqual(attributes, {"*": NO_POLICY})

        attributes = self.iam_db.get_access_policies("/app/resource")
        self.assertEqual(
            attributes,
            {
                "GET": 0b001,
                "POST": 0b110,
                "PUT": 0b110,
                "DELETE": 0b000,
                "OPTIONS": NO_POLICY,
            },
        )

        attributes = self.iam_db.get_access_policies("/app/api")
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

        with open(self.roles_file, "w", encoding="utf-8") as roles:
            self.iam_db._attribute_tree = AttributeNode("")
            roles.write(file_content)

        with self.assertRaises(ValueError):
            self.iam_db.load()

    def test_role_reader_duplicate_attribute(self):
        file_content = "/app/resource\n" + "    GET: role_1\n" + "    GET: role_2\n"

        with open(self.roles_file, "w", encoding="utf-8") as roles:
            self.iam_db._attribute_tree = AttributeNode("")
            roles.write(file_content)

        with self.assertRaises(ValueError):
            self.iam_db.load()


if __name__ == "__main__":
    unittest.main(verbosity=2)
