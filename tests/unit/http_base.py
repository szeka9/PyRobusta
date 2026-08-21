import os
import sys
import unittest

from pathlib import Path

from unittest.mock import patch, mock_open
from tests.unit.utils import load_module

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from utils import patch_time

patch_time()

from pyrobusta.utils import logging
from pyrobusta.stream import buffer
from pyrobusta.utils import config as config_module


class TestHttpBase(unittest.TestCase):
    """
    Base class for HTTP file server module.
    """

    @classmethod
    def setUpClass(cls):
        cls.base_config = {}
        cls.cwd = os.getcwd()

    def setUp(self):
        # Patch current working directory and config
        import pyrobusta

        pyrobusta.WORKING_DIR = self.cwd.rstrip("/")

        # Patch configuration
        config_data = "\n".join(f"{k}={v}" for k, v in self.base_config.items())
        mock_file = mock_open(read_data=config_data)
        with patch.object(config_module, "open", mock_file):
            config = config_module.Config("")

        logging.set_log_level("off")

        # --------------------------------
        # Workspace, temporary directories
        # --------------------------------
        if "tmp" not in os.listdir(self.cwd):
            os.mkdir(self.cwd + "/tmp")

        if "passwd_file" in self.base_config:
            self.passwd_file = self.cwd + self.base_config["passwd_file"]
            with open(self.passwd_file, "w", encoding="utf-8") as passwd:
                if hasattr(self, "passwd_content"):
                    passwd.write(self.passwd_content)

        if "roles_file" in self.base_config:
            self.roles_file = self.cwd + self.base_config["roles_file"]
            with open(self.roles_file, "w", encoding="utf-8") as roles:
                if hasattr(self, "roles_content"):
                    roles.write(self.roles_content)

        # ------------------------------------------------
        # Load modules, enable optional features
        # ------------------------------------------------
        self.iam_db = None
        if self.base_config.get("http_auth"):
            from pyrobusta.utils.iam import IAMDatabase

            self.iam_db = IAMDatabase(self.passwd_file, self.roles_file)
            self.iam_db.load()

        self.http_module = load_module("pyrobusta/protocol/http.py")
        self.http_module.apply_patches(config)

        if config.http_multipart:
            from pyrobusta.protocol import http_multipart

            http_multipart.apply_patches(self.http_module.HttpEngine, config)

        if config.http_files_api:
            from pyrobusta.protocol import http_file_server

            self.fs_patcher = patch.object(http_file_server, "setup_directories")
            self.fs_patcher.start()
            self.addCleanup(self.fs_patcher.stop)
            http_file_server.apply_patches(
                self.http_module.HttpEngine,
                config,
                self.http_module.HttpEngine.USER_DIRECTORY,
            )

        if config.http_browser_security:
            from pyrobusta.protocol import http_security

            http_security.apply_patches(self.http_module.HttpEngine, config)

        if config.http_auth == "basic":
            from pyrobusta.protocol import http_basic_auth

            http_basic_auth.apply_patches(
                self.http_module.HttpEngine, config, self.iam_db
            )

        self.engine = self.http_module.HttpEngine()

        # --------------------
        # Stream buffers
        # --------------------
        self.rx = buffer.SlidingBuffer(bytearray(1024))
        self.tx = buffer.SlidingBuffer(bytearray(1024))

    def tearDown(self):
        try:
            if "passwd_file" in self.base_config:
                os.remove(self.passwd_file)
            if "roles_file" in self.base_config:
                os.remove(self.roles_file)
        finally:
            super().tearDown()
