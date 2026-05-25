import os
import sys
import unittest
import json

from unittest.mock import patch, mock_open, call

from .utils import load_module, stat_factory


def patch_os_stat(stat_is_file=True):
    def patched(f):
        @patch("pyrobusta.protocol.http_file_server.stat", stat_factory(stat_is_file))
        def decorated(*args, **kwargs):
            return f(*args, **kwargs)

        return decorated

    return patched


class TestFileServerBase(unittest.TestCase):
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


class TestFileServerRetrieve(TestFileServerBase):
    """
    Tests for GET /files/.
    """

    @classmethod
    def setUpClass(cls):
        cls.base_config = {
            "http_serve_files": "True",
            "http_served_paths": "/www",
        }
        # Simplify file-open assertions by treating resources
        # as if they are installed at the root (/) rather than
        # relative to the current working directory.
        cls.cwd = "/"

    @patch_os_stat()
    def test_file_serving_missing_file(self, *_):
        self.engine.url = b"/files/www/nonexistent.js"
        self.engine.method = b"GET"
        self.engine.version = b"HTTP/1.1"
        self.engine.state = self.engine._app_endpoint_st

        self.engine.state(self.rx)

        self.assertEqual(self.engine.status_code, 404)
        self.assertEqual(self.engine.state, None)

    @patch_os_stat()
    def test_file_serving_files_endpoint(self, *_):
        self.engine.url = b"/files/www/scripts.js"
        self.engine.method = b"GET"
        self.engine.version = b"HTTP/1.1"
        self.engine.state = self.engine._app_endpoint_st
        file_content = "data"

        with patch("builtins.open", mock_open(read_data=file_content)) as m:
            self.engine.state(self.rx)
            m.assert_called_once_with("/www/scripts.js", "rb")

        self.assertEqual(self.engine.resp_handler.read(), file_content)
        self.assertEqual(self.engine.status_code, 200)
        self.assertEqual(self.engine.state, None)

    @patch_os_stat()
    def test_file_serving_known_content_type(self, *_):
        self.engine.url = b"/files/www/scripts.js"
        self.engine.method = b"GET"
        self.engine.version = b"HTTP/1.1"
        self.engine.state = self.engine._app_endpoint_st
        file_content = "data"

        with patch("builtins.open", mock_open(read_data=file_content)) as m:
            self.engine.state(self.rx)
            m.assert_called_once_with("/www/scripts.js", "rb")

        self.assertEqual(self.engine.resp_handler.read(), file_content)
        self.assertEqual(
            self.engine._lookup(self.engine.resp_headers, b"content-type"),
            b"application/javascript",
        )
        self.assertEqual(self.engine.status_code, 200)
        self.assertEqual(self.engine.state, None)

    @patch_os_stat()
    def test_file_serving_fallback_content_type(self, *_):
        self.engine.url = b"/files/www/scripts.unknown"
        self.engine.method = b"GET"
        self.engine.version = b"HTTP/1.1"
        self.engine.state = self.engine._app_endpoint_st
        file_content = "data"

        with patch("builtins.open", mock_open(read_data=file_content)) as m:
            self.engine.state(self.rx)
            m.assert_called_once_with("/www/scripts.unknown", "rb")

        self.assertEqual(self.engine.resp_handler.read(), file_content)
        self.assertEqual(
            self.engine._lookup(self.engine.resp_headers, b"content-type"),
            b"application/octet-stream",
        )
        self.assertEqual(self.engine.status_code, 200)
        self.assertEqual(self.engine.state, None)

    @patch_os_stat()
    def test_file_serving_unserved_content_rejected(self, *_):
        self.engine.url = b"/files/unserved/script.js"
        self.engine.method = b"GET"
        self.engine.version = b"HTTP/1.1"
        self.engine.state = self.engine._app_endpoint_st
        file_content = "data"

        with patch("builtins.open", mock_open(read_data=file_content)) as m:
            self.engine.state(self.rx)
            m.assert_not_called()

        self.assertNotEqual(self.engine.resp_handler.read(), file_content)
        self.assertEqual(self.engine.status_code, 403)
        self.assertEqual(self.engine.state, None)

    @patch_os_stat(stat_is_file=False)
    def test_file_serving_directory_path(self):
        self.engine.url = b"/files/www"
        self.engine.method = b"GET"
        self.engine.version = b"HTTP/1.1"
        self.engine.state = self.engine._app_endpoint_st

        self.engine.state(self.rx)

        self.assertNotEqual(self.engine.resp_handler, None)
        self.assertEqual(
            self.engine._lookup(self.engine.resp_headers, b"content-type"),
            b"application/json",
        )
        self.assertEqual(self.engine.status_code, 200)
        self.assertEqual(self.engine.state, None)

    @patch_os_stat()
    def test_file_serving_directory_traversal(self):
        directory_content = ["file1", "file2", "file3"]
        with patch(
            "pyrobusta.protocol.http_file_server.iterate_fs",
            lambda *_: directory_content,
        ):
            traversal_function = self.fs_module._traverse_dir_factory("/www")
            for is_finished in traversal_function(self.tx):
                if is_finished:
                    break

        response = json.loads(bytes(self.tx.peek()))
        response_files = [it["path"] for it in response]
        self.assertListEqual(response_files, directory_content)


class TestFileServerDelete(TestFileServerBase):
    """
    Tests for DELETE /files/.
    """

    @classmethod
    def setUpClass(cls):
        cls.base_config = {
            "http_serve_files": "True",
            "http_served_paths": "/www",
        }
        # Simplify file-open assertions by treating resources
        # as if they are installed at the root (/) rather than
        # relative to the current working directory.
        cls.cwd = "/"

    @patch_os_stat()
    def test_file_serving_missing_file(self, *_):
        self.engine.url = b"/files/www/user_data/nonexistent.js"
        self.engine.method = b"DELETE"
        self.engine.version = b"HTTP/1.1"
        self.engine.state = self.engine._app_endpoint_st

        self.engine.state(self.rx)

        self.assertEqual(self.engine.status_code, 404)
        self.assertEqual(self.engine.state, None)

    @patch_os_stat()
    def test_file_serving_non_user_data_rejected(self, *_):
        self.engine.url = b"/files/www/index.html"
        self.engine.method = b"DELETE"
        self.engine.version = b"HTTP/1.1"
        self.engine.state = self.engine._app_endpoint_st

        self.engine.state(self.rx)

        self.assertEqual(self.engine.status_code, 403)
        self.assertEqual(self.engine.state, None)

    @patch_os_stat()
    def test_file_serving_user_data_deleted(self, *_):
        self.engine.url = b"/files/www/user_data/user_content.json"
        self.engine.method = b"DELETE"
        self.engine.version = b"HTTP/1.1"
        self.engine.state = self.engine._app_endpoint_st

        with patch("pyrobusta.protocol.http_file_server.remove") as m:
            self.engine.state(self.rx)
            m.assert_called_once_with("/www/user_data/user_content.json")

        self.assertEqual(self.engine.status_code, 204)
        self.assertEqual(self.engine.state, None)

    @patch_os_stat(stat_is_file=True)
    def test_file_serving_user_directory_deleted(self, *_):
        self.engine.url = b"/files/www/user_data/user_dir"
        self.engine.method = b"DELETE"
        self.engine.version = b"HTTP/1.1"
        self.engine.state = self.engine._app_endpoint_st

        with patch("pyrobusta.protocol.http_file_server.remove") as m:
            self.engine.state(self.rx)
            m.assert_called_once_with("/www/user_data/user_dir")

        self.assertEqual(self.engine.status_code, 204)
        self.assertEqual(self.engine.state, None)


class TestFileServerUpload(TestFileServerBase):
    """
    Tests for POST /files/.
    """

    @classmethod
    def setUpClass(cls):
        cls.base_config = {
            "http_multipart": "True",
            "http_serve_files": "True",
            "http_served_paths": "/www",
        }
        # Simplify file-open assertions by treating resources
        # as if they are installed at the root (/) rather than
        # relative to the current working directory.
        cls.cwd = "/"

    def test_file_serving_complete_file_upload(self, *_):
        self.engine.url = b"/files/www/user_data/complete.txt"
        self.engine.method = b"PUT"
        self.engine.version = b"HTTP/1.1"

        self.engine.headers["content-length"] = 28
        self.engine.headers["content-type"] = "application/octet-stream"

        self.engine.state = self.engine._app_endpoint_st
        body_part = b"File uploaded for testing.\r\n"
        self.rx.write(body_part)

        with patch("builtins.open", mock_open(read_data=body_part)) as open_mock:
            while self.engine.state is not None:
                self.engine.state(self.rx)

            open_mock.assert_called_once_with("/www/user_data/complete.txt", "wb")

        self.assertEqual(self.engine.status_code, 201)

    def test_file_serving_complete_file_invalid_name(self, *_):
        self.engine.url = b"/files/www/user_data/$test.txt"
        self.engine.method = b"PUT"
        self.engine.version = b"HTTP/1.1"

        self.engine.headers["content-length"] = 28
        self.engine.headers["content-type"] = "application/octet-stream"

        self.engine.state = self.engine._app_endpoint_st
        body_part = b"File uploaded for testing.\r\n"
        self.rx.write(body_part)

        while self.engine.state is not None:
            self.engine.state(self.rx)

        self.assertEqual(self.engine.status_code, 400)

    def test_file_serving_chunked_file_upload(self, *_):
        self.engine.url = b"/files/www/user_data/chunked.txt"
        self.engine.method = b"PUT"
        self.engine.version = b"HTTP/1.1"

        self.engine.headers["transfer-encoding"] = "chunked"
        self.engine.headers["content-type"] = "application/octet-stream"

        self.engine.state = self.engine._recv_chunk_size_st
        body_part = (
            b"14\r\nchunking\r\ntest\r\ncase\r\n"
            b"E\r\nchunking\r\ntest\r\n"
            b"8\r\nchunking\r\n"
            b"0\r\n\r\n"
        )
        self.rx.write(body_part)

        m = mock_open()
        with patch("builtins.open", m) as open_mock, patch(
            "pyrobusta.protocol.http_file_server.rename"
        ) as rename_mock:
            while self.engine.state is not None:
                self.engine.state(self.rx)

            open_mock.assert_has_calls(
                [
                    call(f"/tmp/chunked.txt.{self.engine.id}", "ab"),
                    call(f"/tmp/chunked.txt.{self.engine.id}", "ab"),
                    call(f"/tmp/chunked.txt.{self.engine.id}", "ab"),
                ],
                any_order=True,
            )

            rename_mock.assert_called_once_with(
                f"/tmp/chunked.txt.{self.engine.id}",
                "/www/user_data/chunked.txt",
            )

            handle = m()

            handle.write.assert_has_calls(
                [
                    call(b"chunking\r\ntest\r\ncase"),
                    call(b"chunking\r\ntest"),
                    call(b"chunking"),
                ]
            )

            self.assertEqual(handle.write.call_count, 3)

        self.assertEqual(self.engine.status_code, 201)


class TestFileServerBulkUpload(TestFileServerBase):
    """
    Tests for POST /files/.
    """

    @classmethod
    def setUpClass(cls):
        cls.base_config = {
            "http_multipart": "True",
            "http_serve_files": "True",
            "http_served_paths": "/www",
        }
        # Simplify file-open assertions by treating resources
        # as if they are installed at the root (/) rather than
        # relative to the current working directory.
        cls.cwd = "/"

    def test_file_serving_single_file_upload(self, *_):
        self.engine.url = b"/files"
        self.engine.method = b"POST"
        self.engine.version = b"HTTP/1.1"

        self.engine.headers["content-length"] = 151
        self.engine.headers["content-type"] = "multipart/form-data"

        self.engine.mp_boundary = b"test-boundary"
        self.engine.mp_delimiter = b"--test-boundary\r\n"
        self.engine.mp_last_delimiter = b"--test-boundary--"

        self.engine.state = self.engine._start_multipart_parser_st
        body_part = (
            b"--test-boundary\r\n"
            b'Content-Disposition:form-data;name="complete-file";filename="upload.txt"\r\n'
            b"Content-Type:text/plain\r\n\r\n"
            b"Upload content\r\n"
            b"--test-boundary--"
        )
        self.rx.write(body_part)

        with patch(
            "pyrobusta.protocol.http_file_server.listdir",
            lambda _: [f"upload.txt.{self.engine.id}"],
        ), patch("pyrobusta.protocol.http_file_server.remove") as remove_mock, patch(
            "builtins.open"
        ) as open_mock, patch(
            "pyrobusta.protocol.http_file_server.rename"
        ) as rename_mock:
            while self.engine.state is not None:
                self.engine.state(self.rx)

            remove_mock.assert_called_once_with("/tmp/upload.txt.1")
            open_mock.assert_called_once_with("/tmp/upload.txt.1", "ab")
            rename_mock.assert_called_once_with(
                "/tmp/upload.txt.1", "/www/user_data/upload.txt"
            )

        self.assertEqual(self.engine.status_code, 201)

    def test_file_serving_multiple_file_upload(self, *_):
        self.engine.url = b"/files"
        self.engine.method = b"POST"
        self.engine.version = b"HTTP/1.1"

        self.engine.headers["content-length"] = 287
        self.engine.headers["content-type"] = "multipart/form-data"

        self.engine.mp_boundary = b"test-boundary"
        self.engine.mp_delimiter = b"--test-boundary\r\n"
        self.engine.mp_last_delimiter = b"--test-boundary--"

        self.engine.state = self.engine._start_multipart_parser_st
        body_part = (
            b"--test-boundary\r\n"
            b'Content-Disposition:form-data;name="complete-file";filename="upload1.txt"\r\n'
            b"Content-Type:text/plain\r\n\r\n"
            b"Upload content\r\n"
            b"--test-boundary\r\n"
            b'Content-Disposition:form-data;name="complete-file";filename="upload2.txt"\r\n'
            b"Content-Type:text/plain\r\n\r\n"
            b"Upload content\r\n"
            b"--test-boundary--"
        )
        self.rx.write(body_part)

        with patch(
            "pyrobusta.protocol.http_file_server.listdir",
            lambda _: [
                f"upload1.txt.{self.engine.id}",
                f"upload2.txt.{self.engine.id}",
            ],
        ), patch("pyrobusta.protocol.http_file_server.remove") as remove_mock, patch(
            "builtins.open"
        ) as open_mock, patch(
            "pyrobusta.protocol.http_file_server.rename"
        ) as rename_mock:
            while self.engine.state is not None:
                self.engine.state(self.rx)

            remove_mock_calls = [
                call("/tmp/upload1.txt.1"),
                call("/tmp/upload2.txt.1"),
            ]
            open_mock_calls = [
                call("/tmp/upload1.txt.1", "ab"),
                call("/tmp/upload2.txt.1", "ab"),
            ]
            rename_mock_calls = [
                call("/tmp/upload1.txt.1", "/www/user_data/upload1.txt"),
                call("/tmp/upload2.txt.1", "/www/user_data/upload2.txt"),
            ]

            remove_mock.assert_has_calls(remove_mock_calls)
            open_mock.assert_has_calls(open_mock_calls, any_order=True)
            rename_mock.assert_has_calls(rename_mock_calls)

        self.assertEqual(self.engine.status_code, 201)

    def test_file_serving_single_file_multiple_parts_upload(self, *_):
        self.engine.url = b"/files"
        self.engine.method = b"POST"
        self.engine.version = b"HTTP/1.1"

        self.engine.headers["content-length"] = 287
        self.engine.headers["content-type"] = "multipart/form-data"

        self.engine.mp_boundary = b"test-boundary"
        self.engine.mp_delimiter = b"--test-boundary\r\n"
        self.engine.mp_last_delimiter = b"--test-boundary--"

        self.engine.state = self.engine._start_multipart_parser_st
        body_part = (
            b"--test-boundary\r\n"
            b'Content-Disposition:form-data;name="complete-file";filename="upload1.txt"\r\n'
            b"Content-Type:text/plain\r\n\r\n"
            b"Upload content\r\n"
            b"--test-boundary\r\n"
            b'Content-Disposition:form-data;name="complete-file";filename="upload1.txt"\r\n'
            b"Content-Type:text/plain\r\n\r\n"
            b"Upload content\r\n"
            b"--test-boundary--"
        )
        self.rx.write(body_part)

        with patch(
            "pyrobusta.protocol.http_file_server.listdir",
            lambda _: [
                f"upload1.txt.{self.engine.id}",
            ],
        ), patch("pyrobusta.protocol.http_file_server.remove") as remove_mock, patch(
            "builtins.open"
        ) as open_mock, patch(
            "pyrobusta.protocol.http_file_server.rename"
        ) as rename_mock:
            while self.engine.state is not None:
                self.engine.state(self.rx)

            open_mock_calls = [
                call("/tmp/upload1.txt.1", "ab"),
                call("/tmp/upload1.txt.1", "ab"),
            ]

            remove_mock.assert_called_once_with("/tmp/upload1.txt.1")
            open_mock.assert_has_calls(open_mock_calls, any_order=True)
            rename_mock.assert_called_once_with(
                "/tmp/upload1.txt.1", "/www/user_data/upload1.txt"
            )

        self.assertEqual(self.engine.status_code, 201)
