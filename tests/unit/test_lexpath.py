import unittest
import sys

from unittest.mock import patch
from os import getcwd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

import pyrobusta
from pyrobusta.utils import lexpath


class TestLexPath(unittest.TestCase):
    """
    Base class for lexical path helper functions.
    """

    @classmethod
    def setUpClass(cls):
        cls.config = {}

    def test_path_normalization_virtual_root(self):
        """
        Test lexical path normalization in a UNIX-port environment
        with a virtual root. Simulates the situation where the process
        working directory acts as a virtual filesystem root.
        """
        cwd = getcwd()
        for case in (
            ("", ""),
            ("/", f"{cwd}"),
            ("/path/to/resource", f"{cwd}/path/to/resource"),
            ("/path/to/resource/", f"{cwd}/path/to/resource"),
            ("///path///to///resource///", f"{cwd}/path/to/resource"),
            ("/path/../to/resource", f"{cwd}/to/resource"),
            ("/path/./to/resource", f"{cwd}/path/to/resource"),
            ("/path/../../resource", f"{cwd}/resource"),
            ("/path/../../resource/..", f"{cwd}"),
        ):
            self.assertEqual(lexpath.normalize_path(case[0]), case[1])

    @patch.object(pyrobusta, "WORKING_DIR", "")
    def test_path_normalization_host_root(self):
        """
        Test lexical path normalization assuming the working directory
        is the device root ("/"). This simulates the target device environment
        where all paths are rooted at "/".
        """
        for case in (
            ("", ""),
            ("/", "/"),
            ("/path/to/resource", "/path/to/resource"),
            ("/path/to/resource/", "/path/to/resource"),
            ("///path///to///resource///", "/path/to/resource"),
            ("/path/../to/resource", "/to/resource"),
            ("/path/./to/resource", "/path/to/resource"),
            ("/path/../../resource", "/resource"),
            ("/path/../../resource/..", "/"),
        ):
            self.assertEqual(lexpath.normalize_path(case[0]), case[1])

    @patch.object(pyrobusta, "WORKING_DIR", "")
    def test_path_serving_list(self):
        served_paths = ["/path/to/dir1", "/path/to/dir2"]

        for case in (
            ("", False),
            ("/", False),
            ("/path/to/dir1", True),
            ("/path/to/dir2", True),
            ("/path/to/dir12", False),
            ("/path/to/dir1/file", True),
            ("/path/to/dir2/file", True),
            ("/path/to/other", False),
            ("/path/to", False),
        ):
            self.assertEqual(lexpath.is_child_path_of(case[0], served_paths), case[1])

    @patch.object(pyrobusta, "WORKING_DIR", "")
    def test_path_serving_root(self):
        served_paths = ["/"]

        for case in (
            ("", True),
            ("/", True),
            ("/path/to/served", True),
        ):
            self.assertEqual(lexpath.is_child_path_of(case[0], served_paths), case[1])

    @patch.object(pyrobusta, "WORKING_DIR", "")
    def test_path_serving_none(self):
        served_paths = []

        for case in (
            ("", False),
            ("/", False),
            ("/path/to/served", False),
        ):
            self.assertEqual(lexpath.is_child_path_of(case[0], served_paths), case[1])

    def test_path_segment_validation(self):
        valid_segments = ["file", "dir1", "dir-2", "dir_3", "file.ext", "a"]
        invalid_segments = [
            "",
            ".",
            "..",
            "dir/segment",
            "dir\\segment",
            "/dir/segment/file",
        ]

        for segment in valid_segments:
            self.assertTrue(lexpath.is_path_segment_valid(segment))

        for segment in invalid_segments:
            self.assertFalse(lexpath.is_path_segment_valid(segment))

    def test_file_path_validation(self):
        valid_paths = ["/file", "/dir1/file", "/dir-2/file", "/dir_3/file"]
        invalid_paths = [
            "file",
            "dir1/file",
            "/dir\\segment/file",
            "/",
            "/dir/",
            "/dir/file/",
        ]

        for path in valid_paths:
            self.assertTrue(lexpath.is_file_path_valid(path))

        for path in invalid_paths:
            self.assertFalse(lexpath.is_file_path_valid(path))
