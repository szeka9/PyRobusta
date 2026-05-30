import json

from unittest.mock import patch, mock_open, call

from .utils import stat_factory
from .http_base import TestHttpBase


def patch_os_stat(stat_is_file=True):
    def patched(f):
        @patch("pyrobusta.protocol.http_file_server.stat", stat_factory(stat_is_file))
        def decorated(*args, **kwargs):
            return f(*args, **kwargs)

        return decorated

    return patched


class TestFileServerRetrieve(TestHttpBase):
    """
    Tests for GET /files/.
    """

    @classmethod
    def setUpClass(cls):
        cls.base_config = {
            "http_multipart": "False",
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


class TestFileServerDelete(TestHttpBase):
    """
    Tests for DELETE /files/.
    """

    @classmethod
    def setUpClass(cls):
        cls.base_config = {
            "http_multipart": "False",
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


class TestFileServerUpload(TestHttpBase):
    """
    Tests for POST /files/.
    """

    @classmethod
    def setUpClass(cls):
        cls.base_config = {
            "http_multipart": "False",
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


class TestFileServerBulkUpload(TestHttpBase):
    """
    Tests for POST /files/.
    """

    @classmethod
    def setUpClass(cls):
        cls.base_config = {
            # Bulk upload requires multipart handling
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

            # stale upload is removed
            remove_mock.assert_called_once_with(f"/tmp/upload.txt.{self.engine.id}")

            # file is opened in append mode to allow for chunked uploads, even if the complete
            # file is sent in a single part
            open_mock.assert_called_once_with(f"/tmp/upload.txt.{self.engine.id}", "ab")

            # file is renamed to final destination after upload completion
            rename_mock.assert_called_once_with(
                f"/tmp/upload.txt.{self.engine.id}", "/www/user_data/upload.txt"
            )

            self.assertEqual(remove_mock.call_count, 1)
            self.assertEqual(open_mock.call_count, 1)
            self.assertEqual(rename_mock.call_count, 1)

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
                call(f"/tmp/upload1.txt.{self.engine.id}"),
                call(f"/tmp/upload2.txt.{self.engine.id}"),
            ]
            open_mock_calls = [
                call(f"/tmp/upload1.txt.{self.engine.id}", "ab"),
                call(f"/tmp/upload2.txt.{self.engine.id}", "ab"),
            ]
            rename_mock_calls = [
                call(
                    f"/tmp/upload1.txt.{self.engine.id}", "/www/user_data/upload1.txt"
                ),
                call(
                    f"/tmp/upload2.txt.{self.engine.id}", "/www/user_data/upload2.txt"
                ),
            ]

            remove_mock.assert_has_calls(remove_mock_calls)
            open_mock.assert_has_calls(open_mock_calls, any_order=True)
            rename_mock.assert_has_calls(rename_mock_calls)

            self.assertEqual(remove_mock.call_count, 2)
            self.assertEqual(open_mock.call_count, 2)
            self.assertEqual(rename_mock.call_count, 2)

        self.assertEqual(self.engine.status_code, 201)

    def test_file_serving_single_file_multiple_parts_upload(self, *_):
        self.engine.url = b"/files"
        self.engine.method = b"POST"
        self.engine.version = b"HTTP/1.1"

        self.engine.headers["content-length"] = 285
        self.engine.headers["content-type"] = "multipart/form-data"

        self.engine.mp_boundary = b"test-boundary"
        self.engine.mp_delimiter = b"--test-boundary\r\n"
        self.engine.mp_last_delimiter = b"--test-boundary--"

        self.engine.state = self.engine._start_multipart_parser_st
        body_part = (
            b"--test-boundary\r\n"
            b'Content-Disposition:form-data;name="file-chunk-1";filename="upload1.txt"\r\n'
            b"Content-Type:text/plain\r\n\r\n"
            b"Upload content\r\n"
            b"--test-boundary\r\n"
            b'Content-Disposition:form-data;name="file-chunk-2";filename="upload1.txt"\r\n'
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
                call(f"/tmp/upload1.txt.{self.engine.id}", "ab"),
                call(f"/tmp/upload1.txt.{self.engine.id}", "ab"),
            ]

            remove_mock.assert_called_once_with(f"/tmp/upload1.txt.{self.engine.id}")
            open_mock.assert_has_calls(open_mock_calls, any_order=True)
            rename_mock.assert_called_once_with(
                f"/tmp/upload1.txt.{self.engine.id}", "/www/user_data/upload1.txt"
            )

            self.assertEqual(remove_mock.call_count, 1)
            self.assertEqual(open_mock.call_count, 2)
            self.assertEqual(rename_mock.call_count, 1)

        self.assertEqual(self.engine.status_code, 201)

    def test_file_serving_multiple_file_chunked_upload(self, *_):
        self.engine.url = b"/files"
        self.engine.method = b"POST"
        self.engine.version = b"HTTP/1.1"

        self.engine.headers["content-length"] = 548
        self.engine.headers["content-type"] = "multipart/form-data"

        self.engine.mp_boundary = b"test-boundary"
        self.engine.mp_delimiter = b"--test-boundary\r\n"
        self.engine.mp_last_delimiter = b"--test-boundary--"

        self.engine.state = self.engine._start_multipart_parser_st
        body_part = (
            b"--test-boundary\r\n"
            b'Content-Disposition:form-data;name="file-chunk-1";filename="upload1.txt"\r\n'
            b"Content-Type:text/plain\r\n\r\n"
            b"Upload content #1\r\n"
            b"--test-boundary\r\n"
            b'Content-Disposition:form-data;name="file-chunk-2";filename="upload2.txt"\r\n'
            b"Content-Type:text/plain\r\n\r\n"
            b"Upload content #1\r\n"
            b"--test-boundary\r\n"
            b'Content-Disposition:form-data;name="file-chunk-3";filename="upload1.txt"\r\n'
            b"Content-Type:text/plain\r\n\r\n"
            b"Upload content #2\r\n"
            b"--test-boundary\r\n"
            b'Content-Disposition:form-data;name="file-chunk-4";filename="upload2.txt"\r\n'
            b"Content-Type:text/plain\r\n\r\n"
            b"Upload content #2\r\n"
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
                call(f"/tmp/upload1.txt.{self.engine.id}"),
                call(f"/tmp/upload2.txt.{self.engine.id}"),
            ]
            open_mock_calls = [
                call(f"/tmp/upload1.txt.{self.engine.id}", "ab"),
                call(f"/tmp/upload2.txt.{self.engine.id}", "ab"),
                call(f"/tmp/upload1.txt.{self.engine.id}", "ab"),
                call(f"/tmp/upload2.txt.{self.engine.id}", "ab"),
            ]
            rename_mock_calls = [
                call(
                    f"/tmp/upload1.txt.{self.engine.id}", "/www/user_data/upload1.txt"
                ),
                call(
                    f"/tmp/upload2.txt.{self.engine.id}", "/www/user_data/upload2.txt"
                ),
            ]

            remove_mock.assert_has_calls(remove_mock_calls)
            open_mock.assert_has_calls(open_mock_calls, any_order=True)
            rename_mock.assert_has_calls(rename_mock_calls)

            self.assertEqual(remove_mock.call_count, 2)
            self.assertEqual(open_mock.call_count, 4)
            self.assertEqual(rename_mock.call_count, 2)

        self.assertEqual(self.engine.status_code, 201)
