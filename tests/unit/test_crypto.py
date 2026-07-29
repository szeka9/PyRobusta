import os
import unittest
import hashlib
import hmac
import random

from tests.unit.utils import load_module


class TestCryptoHmacSha256(unittest.TestCase):
    """
    Test class for HMAC-SHA256, based on RFC4231.
    """

    @classmethod
    def setUpClass(cls):
        cls.config = {}

    def setUp(self):
        self.crypto_module = load_module("pyrobusta/utils/crypto.py")

    def test_hmac_sha256_valid(self):
        for test_vector in (
            (
                bytes([0x0B]) * 20,
                b"Hi There",
                bytes.fromhex(
                    "b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7"
                ),
            ),
            (
                b"Jefe",
                b"what do ya want for nothing?",
                bytes.fromhex(
                    "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843"
                ),
            ),
            (
                bytes([0xAA]) * 20,
                bytes([0xDD]) * 50,
                bytes.fromhex(
                    "773ea91e36800e46854db8ebd09181a72959098b3ef8c122d9635514ced565fe"
                ),
            ),
            (
                bytes.fromhex("0102030405060708090A0B0C0D0E0F10111213141516171819"),
                bytes([0xCD]) * 50,
                bytes.fromhex(
                    "82558a389a443c0ea4cc819899f2083a85f0faa3e578f8077a2e3ff46729665b"
                ),
            ),
            (
                bytes([0x0C]) * 20,
                b"Test With Truncation",
                bytes.fromhex("a3b6167473100ee06e0c796c2955552b"),
                16,  # compare only the first 16 bytes
            ),
            (
                bytes([0xAA]) * 131,
                b"Test Using Larger Than Block-Size Key - Hash Key First",
                bytes.fromhex(
                    "60e431591ee0b67f0d8a26aacbf5b77f8e0bc6213728c5140546040f0ee37f54"
                ),
            ),
            (
                bytes([0xAA]) * 131,
                b"This is a test using a larger than block-size key and a larger "
                + b"than block-size data. The key needs to be hashed before being "
                + b"used by the HMAC algorithm.",
                bytes.fromhex(
                    "9b09ffa71b942fcb27635fbcd5b0e944bfdc63644f0713938a7f51535c3a35e2"
                ),
            ),
        ):
            truncate = None
            if len(test_vector) == 3:
                key, msg, expected = test_vector
            else:
                key, msg, expected, truncate = test_vector

            hs = self.crypto_module.HmacSha256(key)
            actual = hs.digest(msg)
            reference = hmac.new(key, msg, hashlib.sha256).digest()

            if truncate is None:
                self.assertEqual(expected, actual)
            else:
                self.assertEqual(expected, actual[:truncate])

            self.assertEqual(reference, actual)


class TestCryptoPbkdf2(unittest.TestCase):
    """
    Test class for PBKDF2, based on RFC6070.
    """

    @classmethod
    def setUpClass(cls):
        cls.config = {}

    def setUp(self):
        self.crypto_module = load_module("pyrobusta/utils/crypto.py")

    def test_pbkdf2_sha256_rfc(self):
        for password, salt, iterations, dklen, expected in (
            (
                b"password",
                b"salt",
                1,
                20,
                bytes.fromhex("120fb6cffcf8b32c43e7225256c4f837a86548c9"),
            ),
            (
                b"password",
                b"salt",
                2,
                20,
                bytes.fromhex("ae4d0c95af6b46d32d0adff928f06dd02a303f8e"),
            ),
            (
                b"password",
                b"salt",
                4096,
                20,
                bytes.fromhex("c5e478d59288c841aa530db6845c4c8d962893a0"),
            ),
            (
                b"passwordPASSWORDpassword",
                b"saltSALTsaltSALTsaltSALTsaltSALTsalt",
                4096,
                25,
                bytes.fromhex("348c89dbcbd32b2f32d814b8116e84cf2b17347ebc1800181c"),
            ),
            (
                b"pass\0word",
                b"sa\0lt",
                4096,
                16,
                bytes.fromhex("89b69d0516f829893c696226650a8687"),
            ),
        ):
            reference = hashlib.pbkdf2_hmac(
                "sha256",
                password,
                salt,
                iterations,
                dklen,
            )
            actual = self.crypto_module.pbkdf2_sha256(
                password,
                salt,
                iterations,
                dklen,
            )
            self.assertEqual(expected, actual)
            self.assertEqual(reference, actual)

    def test_pbkdf2_sha256_valid(self):
        for password, salt, iterations, dklen in (
            (b"password", b"salt", 1, 32),
            (b"password", b"salt", 16000, 32),
            (b"password", b"salt", 100, 64),
            (b"", b"", 1, 32),
        ):
            expected = hashlib.pbkdf2_hmac(
                "sha256",
                password,
                salt,
                iterations,
                dklen,
            )
            actual = self.crypto_module.pbkdf2_sha256(
                password,
                salt,
                iterations,
                dklen,
            )
            self.assertEqual(expected, actual)

    def test_pbkdf2_sha256_invalid(self):
        for test_vector in (
            (b"password", b"salt", 0, 32),
            (b"password", b"salt", -1, 32),
            (b"password", b"salt", 1, 0),
            (b"password", b"salt", 1, -1),
        ):
            password, salt, iterations, dklen = test_vector
            with self.assertRaises(ValueError):
                self.crypto_module.pbkdf2_sha256(
                    password,
                    salt,
                    iterations,
                    dklen,
                )

    def test_pbkdf2_sha256_edge_case(self):
        for test_vector in (
            (b"", os.urandom(16), 1, 32),  # Empty password
            (b"password", b"", 1, 32),  # Empty salt
            (b"password", b"salt", 1, 1),  # One byte output
            (b"password", b"salt", 100, 33),  # Two PBKDF2 blocks
            (b"password", b"salt", 100, 100),  # Multiple PBKDF2 blocks
        ):
            password, salt, iterations, dklen = test_vector

            expected = hashlib.pbkdf2_hmac(
                "sha256",
                password,
                salt,
                iterations,
                dklen,
            )

            actual = self.crypto_module.pbkdf2_sha256(
                password,
                salt,
                iterations,
                dklen,
            )
            self.assertEqual(expected, actual)

    def test_pbkdf2_sha256_randomized(self):
        for _ in range(100):
            password = os.urandom(random.randint(0, 128))
            salt = os.urandom(random.randint(0, 64))
            iterations = random.randint(1, 1000)
            dklen = random.randint(1, 100)

            expected = hashlib.pbkdf2_hmac(
                "sha256",
                password,
                salt,
                iterations,
                dklen,
            )

            actual = self.crypto_module.pbkdf2_sha256(
                password,
                salt,
                iterations,
                dklen,
            )
            self.assertEqual(expected, actual)
