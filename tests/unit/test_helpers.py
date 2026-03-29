import unittest
from unittest.mock import patch
from os import getcwd

from .utils import load_module


class TestHelpers(unittest.TestCase):
    """
    Base class for stat machine tests.
    """

    @classmethod
    def setUpClass(cls):
        cls.config = {}

    def setUp(self):
        self.helpers_module = load_module("pyrobusta/utils/helpers.py")

    def test_path_normalization_virtual_root(self):
        """
        Test lexical path normalization in a Unix-port environment
        with a virtual root. Simulates the situation where the process
        working directory acts as a virtual filesystem root.
        """
        cwd = getcwd()
        for case in (
            ("", ""),
            ("/path/to/resource", f"{cwd}/path/to/resource"),
            ("/path/to/resource/", f"{cwd}/path/to/resource"),
            ("///path///to///resource///", f"{cwd}/path/to/resource"),
            ("/path/../to/resource", f"{cwd}/to/resource"),
            ("/path/./to/resource", f"{cwd}/path/to/resource"),
            ("/path/../../resource", f"{cwd}/resource"),
            ("/path/../../resource/..", f"{cwd}"),
        ):
            self.assertEqual(self.helpers_module.normalize_path(case[0]), case[1])

    @patch("pyrobusta.utils.helpers.getcwd", return_value="/")
    def test_path_normalization_host_root(self, _):
        """
        Test lexical path normalization assuming the working directory
        is the device root ("/"). This simulates the target device environment
        where all paths are rooted at "/".
        """
        for case in (
            ("", ""),
            ("/path/to/resource", "/path/to/resource"),
            ("/path/to/resource/", "/path/to/resource"),
            ("///path///to///resource///", "/path/to/resource"),
            ("/path/../to/resource", "/to/resource"),
            ("/path/./to/resource", "/path/to/resource"),
            ("/path/../../resource", "/resource"),
            ("/path/../../resource/..", "/"),
        ):
            self.assertEqual(self.helpers_module.normalize_path(case[0]), case[1])
