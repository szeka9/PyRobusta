import os
import sys
import unittest

from unittest.mock import patch, mock_open
from tests.unit.test_buffer import load_module


class TestHttpBase(unittest.TestCase):
    """
    Base class for HTTP file server module.
    """

    @classmethod
    def setUpClass(cls):
        cls.base_config = {}
        cls.cwd = os.getcwd()

    def setUp(self):
        # -------------------------------
        # Patch current working directory
        # -------------------------------
        self.helpers_module = load_module("pyrobusta/utils/helpers.py")
        self.cwd_patcher = patch.object(
            self.helpers_module, "getcwd", return_value=self.cwd
        )
        self.cwd_patcher.start()
        self.addCleanup(self.cwd_patcher.stop)

        # -------------------
        # Patch config module
        # -------------------
        self.config = dict(self.base_config)
        self.config_module = load_module("pyrobusta/utils/config.py")
        self.module_patcher = patch.dict(
            sys.modules,
            {"pyrobusta.utils.config": self.config_module},
        )
        self.module_patcher.start()
        self.addCleanup(self.module_patcher.stop)

        def open_side_effect(*args, **kwargs):
            data = "\n".join(f"{k}={v}" for k, v in self.config.items())
            return mock_open(read_data=data)(*args, **kwargs)

        self.open_patcher = patch.object(
            self.config_module,
            "open",
            side_effect=open_side_effect,
        )
        self.open_patcher.start()
        self.addCleanup(self.open_patcher.stop)

        # ------------------------------------------------
        # Load remaining modules, enable optional features
        # ------------------------------------------------
        self.http_module = load_module("pyrobusta/protocol/http.py")
        self.fs_module = load_module("pyrobusta/protocol/http_file_server.py")
        self.multipart_module = load_module("pyrobusta/protocol/http_multipart.py")

        self.fs_patcher = patch.object(self.fs_module, "setup_directories")
        self.fs_patcher.start()
        self.addCleanup(self.fs_patcher.stop)

        self.http_module.enable_optional_features()
        self.engine = self.http_module.HttpEngine()

        # --------------------
        # HTTP engine, buffers
        # --------------------
        buffer_module = load_module("pyrobusta/stream/buffer.py")
        self.rx = buffer_module.SlidingBuffer(bytearray(1024))
        self.tx = buffer_module.SlidingBuffer(bytearray(1024))
