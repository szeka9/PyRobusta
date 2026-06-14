import os
import unittest

from unittest import mock
from unittest.mock import patch, mock_open

from .utils import stat_factory
from .http_base import TestHttpBase


class TestWebStateMachineHelpers(TestHttpBase):
    """
    Tests for state machine helper functions.
    """

    @classmethod
    def setUpClass(cls):
        cls.base_config = {"http_multipart": "False", "http_files_api": "False"}
        cls.cwd = os.getcwd()

    def test_response_header_setter(self):
        self.engine.url = b"/test"
        self.engine.method = b"GET"
        self.engine.version = b"HTTP/1.1"

        self.engine.set_response_header(b"content-type", b"application/json")
        self.engine.set_response_header(b"transfer-encoding", b"chunked")

        self.assertEqual(
            self.engine.get_response_header(b"content-type"), b"application/json"
        )
        self.assertEqual(
            self.engine.get_response_header(b"transfer-encoding"), b"chunked"
        )

    def test_response_header_setter_override(self):
        self.engine.url = b"/test"
        self.engine.method = b"GET"
        self.engine.version = b"HTTP/1.1"

        self.engine.set_response_header(b"content-type", b"application/json")
        self.engine.set_response_header(b"connection", b"keep-alive")

        self.engine.set_response_header(b"content-type", b"text/plain")
        self.engine.set_response_header(b"connection", b"close")

        self.assertEqual(
            self.engine.get_response_header(b"content-type"), b"text/plain"
        )
        self.assertEqual(self.engine.get_response_header(b"connection"), b"close")

    def test_generate_response_head(self):
        self.engine.url = b"/test"
        self.engine.method = b"GET"
        self.engine.version = b"HTTP/1.1"

        self.engine.set_response_header(b"content-type", b"application/json")
        self.engine.set_response_header(b"transfer-encoding", b"chunked")

        self.engine.terminate(200)

        self.engine.write_response_head(self.tx)
        self.assertEqual(bytes(self.tx.peek()).find(b"HTTP/1.1 200 OK\r\n"), 0)
        self.assertNotEqual(
            bytes(self.tx.peek()).find(b"\r\ncontent-type: application/json\r\n"), -1
        )
        self.assertNotEqual(
            bytes(self.tx.peek()).find(b"\r\ntransfer-encoding: chunked\r\n"), -1
        )

    def test_generate_response_head_override(self):
        self.engine.url = b"/test"
        self.engine.method = b"GET"
        self.engine.version = b"HTTP/1.1"

        self.engine.set_response_header(b"content-type", b"application/json")
        self.engine.set_response_header(b"date", b"Tue, 29 Feb 2026 15:32:12 GMT")
        self.engine.terminate(200)

        self.engine.set_response_header(b"content-type", b"text/plain")
        self.engine.set_response_header(b"date", b"Tue, 29 Feb 2026 15:32:13 GMT")
        self.engine.terminate(400)

        self.engine.write_response_head(self.tx)
        self.assertEqual(bytes(self.tx.peek()).find(b"HTTP/1.1 400 Bad Request\r\n"), 0)
        self.assertNotEqual(
            bytes(self.tx.peek()).find(b"\r\ncontent-type: text/plain\r\n"), -1
        )
        self.assertNotEqual(
            bytes(self.tx.peek()).find(b"\r\ndate: Tue, 29 Feb 2026 15:32:13 GMT\r\n"),
            -1,
        )


class TestWebStateMachine(TestHttpBase):
    """
    Tests for the core functionality of the state machine.
    """

    @classmethod
    def setUpClass(cls):
        cls.base_config = {"http_multipart": "False", "http_files_api": "False"}
        cls.cwd = os.getcwd()

    def test_status_parsing_valid(self):
        request = b"GET /index.html HTTP/1.1\r\nContent-Length:10"

        for i in range(len(request)):
            self.rx.write(request[i : i + 1])
            self.engine.state(self.rx)

        self.assertEqual(self.engine.method, b"GET")
        self.assertEqual(self.engine.url, b"/index.html")
        self.assertEqual(self.engine.version, b"HTTP/1.1")
        self.assertEqual(self.rx.peek(), b"Content-Length:10")
        self.assertEqual(self.engine.state, self.engine._parse_headers_st)

    def test_status_parsing_incomplete_line(self):
        request = b"GET /index.html HTTP/1.1"

        for i in range(len(request)):
            self.rx.write(request[i : i + 1])
            self.engine.state(self.rx)
            if self.engine.state is None:
                break

        self.assertEqual(self.engine.method, None)
        self.assertEqual(self.engine.url, None)
        self.assertEqual(self.engine.version, None)
        self.assertEqual(self.engine.state, self.engine._parse_request_line_st)

    def test_status_parsing_unsupported_method(self):
        request = b"NOTSUPORTED /index.html HTTP/1.1\r\n"

        for i in range(len(request)):
            self.rx.write(request[i : i + 1])
            self.engine.state(self.rx)
            if self.engine.state is None:
                break

        self.assertEqual(self.engine.method, b"NOTSUPORTED")
        self.assertEqual(self.engine.url, b"/index.html")
        self.assertEqual(self.engine.version, b"HTTP/1.1")
        self.assertEqual(self.engine.state, None)
        self.assertEqual(self.engine.status_code, 405)

    def test_status_parsing_unsupported_version(self):
        request = b"GET /index.html HTTP/2\r\n"

        for i in range(len(request)):
            self.rx.write(request[i : i + 1])
            self.engine.state(self.rx)
            if self.engine.state is None:
                break

        self.assertEqual(self.engine.method, b"GET")
        self.assertEqual(self.engine.url, b"/index.html")
        self.assertEqual(self.engine.version, b"HTTP/2")
        self.assertEqual(self.engine.state, None)
        self.assertEqual(self.engine.status_code, 505)

    def test_header_parsing_valid(self):
        self.engine.state = self.engine._parse_headers_st
        request = b"Content-Length:10\r\nContent-Type:application/json\r\n\r\n"

        for i in range(len(request)):
            self.rx.write(request[i : i + 1])
            self.engine.state(self.rx)

        self.assertDictEqual(
            {"content-length": 10, "content-type": "application/json"},
            self.engine.headers,
        )
        self.assertEqual(self.rx.peek(), b"")
        self.assertEqual(self.engine.state, self.engine._route_request_st)

    def test_header_parsing_incomplete_header(self):
        request = b"GET /index.html HTTP/1.1\r\nContent-Type\r\n\r\n"

        with self.assertRaises(self.http_module.InvalidHeaders):
            for i in range(len(request)):
                self.rx.write(request[i : i + 1])
                self.engine.state(self.rx)

    def test_header_parsing_error(self):
        for case in (
            b"",
            b":",
            b": value",
            b" leading-space: value",
            b"space in header name: value",
            b"new-line-in-header:\nvalue",
        ):
            with self.assertRaises(self.http_module.InvalidHeaders):
                self.engine._parse_headers(case)

    def test_header_parsing_combined(self):
        for case in (
            (
                b"field-name: value1\r\nfield-name: value2",
                {"field-name": "value1, value2"},
            ),
            (
                b"field-name: \r\nfield-name: value1\r\nfield-name:\r\nfield-name: value2",
                {"field-name": "value1, value2"},
            ),
        ):
            self.assertEqual(self.engine._parse_headers(case[0]), case[1])

    def test_routing_unsupported_method(self):
        self.engine.state = self.engine._route_request_st
        self.engine.url = b"/api/test"
        self.engine.method = b"GET"
        self.engine.version = b"HTTP/1.1"

        test_callback = mock.Mock()
        self.engine.register("/api/test", test_callback, "POST")

        self.engine.state(self.rx)

        self.assertEqual(self.engine.status_code, 405)
        self.assertEqual(self.engine.state, None)
        self.assertIn(b"allow", self.engine.resp_headers)
        self.assertIn(b"POST", self.engine.resp_headers)

    def test_routing_options_method(self):
        self.engine.state = self.engine._route_request_st
        self.engine.url = b"/api/test"
        self.engine.method = b"OPTIONS"
        self.engine.version = b"HTTP/1.1"

        test_callback = mock.Mock()
        self.engine.register("/api/test", test_callback, "GET")
        self.engine.register("/api/test", test_callback, "POST")
        self.engine.register("/api/test", test_callback, "PUT")

        self.engine.state(self.rx)

        self.assertEqual(self.engine.status_code, 204)
        self.assertEqual(self.engine.state, None)
        self.assertIn(b"allow", self.engine.resp_headers)
        self.assertIn(b"GET, POST, PUT", self.engine.resp_headers)

    def test_routing_get_method(self):
        self.engine.state = self.engine._route_request_st
        self.engine.url = b"/api/test"
        self.engine.method = b"GET"
        self.engine.version = b"HTTP/1.1"
        test_response = b"[test-response]"

        test_callback = mock.Mock()
        test_callback.return_value = ("text/plain", test_response)
        self.engine.register("/api/test", test_callback, "GET")

        while self.engine.state is not None:
            self.engine.state(self.rx)

        self.assertEqual(self.engine.status_code, 200)
        self.assertEqual(self.engine.state, None)
        self.assertEqual(
            int(self.engine._lookup(self.engine.resp_headers, b"content-length")),
            len(test_response),
        )
        self.assertEqual(self.engine.resp_handler.read(), test_response)

    def test_routing_head_method(self):
        self.engine.state = self.engine._route_request_st
        self.engine.url = b"/api/test"
        self.engine.method = b"HEAD"
        self.engine.version = b"HTTP/1.1"
        test_response = b"[test-response]"

        test_callback = mock.Mock()
        test_callback.return_value = ("text/plain", test_response)
        self.engine.register("/api/test", test_callback, "GET")

        while self.engine.state is not None:
            self.engine.state(self.rx)

        self.assertEqual(self.engine.status_code, 200)
        self.assertEqual(self.engine.state, None)
        self.assertEqual(
            int(self.engine._lookup(self.engine.resp_headers, b"content-length")),
            len(test_response),
        )
        self.assertEqual(self.engine.resp_handler, None)

    def test_simple_query_parameter(self):
        request = b"GET /api/test?param HTTP/1.1\r\n"

        for i in range(len(request)):
            self.rx.write(request[i : i + 1])
            self.engine.state(self.rx)

        self.assertEqual(self.engine.query, "param")

    def test_pct_encoded_query_parameter(self):
        def pct_encode(b):
            out = []
            for c in b:
                out.append(f"%{ord(c):02X}")
            return "".join(out)

        unsafe_chars = ":/?#[]@!$&'()*+,;=% "
        request = b"GET /api/test?safe_chars.%s HTTP/1.1\r\n" % pct_encode(
            unsafe_chars
        ).encode("ascii")

        for i in range(len(request)):
            self.rx.write(request[i : i + 1])
            self.engine.state(self.rx)

        self.assertEqual(self.engine.query, f"safe_chars.{unsafe_chars}")

    def test_single_url_encoded_query_parameter(self):
        request = b"GET /api/test?param=value HTTP/1.1\r\n"

        for i in range(len(request)):
            self.rx.write(request[i : i + 1])
            self.engine.state(self.rx)

        self.assertEqual(self.engine.get_query_param("param"), "value")

    def test_multiple_url_encoded_query_parameter(self):
        request = (
            b"GET /api/test?param1=value1&param2=value2&param3=value3 HTTP/1.1\r\n"
        )

        for i in range(len(request)):
            self.rx.write(request[i : i + 1])
            self.engine.state(self.rx)

        self.assertEqual(
            self.engine.get_query_param("param1"),
            "value1",
        )
        self.assertEqual(
            self.engine.get_query_param("param2"),
            "value2",
        )
        self.assertEqual(
            self.engine.get_query_param("param3"),
            "value3",
        )

    def test_empty_or_missing_url_encoded_query_parameter(self):
        request = b"GET /api/test?param1=&param2= HTTP/1.1\r\n"

        for i in range(len(request)):
            self.rx.write(request[i : i + 1])
            self.engine.state(self.rx)

        self.assertEqual(
            self.engine.get_query_param("param1"),
            "",
        )
        self.assertEqual(
            self.engine.get_query_param("param2"),
            "",
        )
        self.assertEqual(
            self.engine.get_query_param("param3", "default"),
            "default",
        )

        with self.assertRaises(KeyError):
            self.engine.get_query_param("param3")

    def test_overlapping_url_encoded_query_parameter(self):
        request = b"GET /api/test?data=value1&ta=value2&a=value3 HTTP/1.1\r\n"

        for i in range(len(request)):
            self.rx.write(request[i : i + 1])
            self.engine.state(self.rx)

        self.assertEqual(
            self.engine.get_query_param("data"),
            "value1",
        )
        self.assertEqual(
            self.engine.get_query_param("ta"),
            "value2",
        )
        self.assertEqual(
            self.engine.get_query_param("a"),
            "value3",
        )

    def test_url_path_matching(self):
        for case in (
            (b"", b""),
            (b"/", b"/"),
            (b"///", b"///"),
            (b"/path/to/resource", b"/path/to/resource"),
            (b"/path/to/specific/resource", b"/path/to/{wildcard}/resource"),
            (b"anything", b"{wildcard}"),
            (b"path/to/resource", b"path/to/{wildcard}"),
            (b"path/to/resource", b"path/to/{wildcard:path}"),
            (b"path/to/resource/", b"path/to/{wildcard:path}"),
            (
                b"path/to/resource/subresource/subsubresource",
                b"path/to/{wildcard:path}",
            ),
        ):
            self.assertEqual(self.engine._is_matching_url_path(case[0], case[1]), True)

    def test_url_path_matching_mismatch(self):
        for case in (
            (b"", b"/"),
            (b"", b"{wildcard}"),
            (b"", b"{wildcard:path}"),
            (b"/path/to/resource/subresource", b"/path/to/resource"),
            (b"/path/to/", b"/path/to/{wildcard}"),
            (b"/path/to/", b"/path/to/{wildcard:path}"),
            (b"/to/resource", b"{wildcard}/to/resource"),
            (b"path/to/resource/subresource/subsubresource", b"path/to/{wildcard}"),
        ):
            self.assertEqual(self.engine._is_matching_url_path(case[0], case[1]), False)

    def test_chunked_transfer_encoding_valid(self):
        self.engine.url = b"/api/test"
        self.engine.method = b"GET"
        self.engine.version = b"HTTP/1.1"
        self.engine.headers["transfer-encoding"] = "chunked"
        self.engine.state = self.engine._recv_chunk_size_st

        test_callback = mock.Mock(return_value=("text/plain", "OK"))
        self.engine.register("/api/test", test_callback, "GET")

        for chunk in (
            b"14\r\nchunking\r\ntest\r\ncase\r\n",
            b"E\r\nchunking\r\ntest\r\n",
            b"8\r\nchunking\r\n",
            b"0\r\n\r\n",
        ):
            for i in range(len(chunk)):
                self.rx.write(chunk[i : i + 1])
                self.engine.state(self.rx)

            self.assertEqual(self.engine.state, self.engine._app_endpoint_st)
            self.engine.state(self.rx)
            size_delimiter = chunk.find(b"\r\n")
            test_callback.assert_called_with(
                self.engine, chunk[size_delimiter + 2 : -2]
            )

        self.assertEqual(self.engine.status_code, 200)
        self.assertEqual(self.engine.state, None)

    def test_chunked_transfer_encoding_invalid_chunk_size_smaller(self):
        self.engine.url = b"/api/test"
        self.engine.method = b"GET"
        self.engine.version = b"HTTP/1.1"
        self.engine.headers["transfer-encoding"] = "chunked"
        self.engine.state = self.engine._recv_chunk_size_st

        test_callback = mock.Mock(return_value=("text/plain", "OK"))
        self.engine.register("/api/test", test_callback, "GET")

        with self.assertRaises(self.http_module.InvalidContentLength):
            chunk = b"2\r\nchunking\r\n"
            for i in range(len(chunk)):
                self.rx.write(chunk[i : i + 1])
                self.engine.state(self.rx)

    def test_chunked_transfer_encoding_chunk_incomplete(self):
        self.engine.url = b"/api/test"
        self.engine.method = b"GET"
        self.engine.version = b"HTTP/1.1"
        self.engine.headers["transfer-encoding"] = "chunked"
        self.engine.state = self.engine._recv_chunk_size_st

        test_callback = mock.Mock(return_value=("text/plain", "OK"))
        self.engine.register("/api/test", test_callback, "GET")

        chunk = b"FF\r\nchunking\r\n"
        for i in range(len(chunk)):
            self.rx.write(chunk[i : i + 1])
            self.engine.state(self.rx)
            if self.engine.state is None:
                break

        self.assertEqual(self.engine.status_code, None)
        self.assertEqual(self.engine.state, self.engine._recv_chunk_st)

    def test_payload_length_matches_content_length(self):
        self.engine.url = b"/api/test"
        self.engine.method = b"POST"
        self.engine.version = b"HTTP/1.1"
        self.engine.headers["content-length"] = 11
        self.engine.state = self.engine._recv_payload_st

        test_callback = mock.Mock(return_value=("text/plain", "OK"))
        self.engine.register("/api/test", test_callback, "POST")

        payload = b"hello world"
        for i in range(len(payload)):
            self.rx.write(payload[i : i + 1])
            self.engine.state(self.rx)

        while self.engine.state is not None:
            self.engine.state(self.rx)

        self.assertEqual(self.engine.status_code, 200)
        self.assertEqual(self.engine.state, None)
        test_callback.assert_called_with(self.engine, payload)

    def test_payload_length_exceeds_content_length(self):
        """
        Test if the engine correctly reads the payload until content-length
        and ignores remaining data. The remaining data should not cause an
        error since the parser should be able to read it in a subsequent request
        if the connection is kept alive.
        """

        self.engine.url = b"/api/test"
        self.engine.method = b"POST"
        self.engine.version = b"HTTP/1.1"
        self.engine.headers["content-length"] = 11
        self.engine.state = self.engine._recv_payload_st

        test_callback = mock.Mock(return_value=("text/plain", "OK"))
        self.engine.register("/api/test", test_callback, "POST")

        payload = b"hello world!"
        for i in range(len(payload)):
            self.rx.write(payload[i : i + 1])
            self.engine.state(self.rx)
            if self.engine.state is None:
                break

        while self.engine.state is not None:
            self.engine.state(self.rx)

        self.assertEqual(self.engine.status_code, 200)
        self.assertEqual(self.engine.state, None)
        test_callback.assert_called_with(self.engine, b"hello world")
        self.assertEqual(
            self.rx.peek(), b"!"
        )  # Remaining data after content-length is ignored

    def test_payload_length_less_than_content_length(self):
        """
        Test if the engine correctly waits for the full payload when
        content-length is not yet satisfied.
        """
        self.engine.url = b"/api/test"
        self.engine.method = b"POST"
        self.engine.version = b"HTTP/1.1"
        self.engine.headers["content-length"] = 11
        self.engine.state = self.engine._recv_payload_st

        test_callback = mock.Mock(return_value=("text/plain", "OK"))
        self.engine.register("/api/test", test_callback, "POST")

        payload = b"hello"
        for i in range(len(payload)):
            self.rx.write(payload[i : i + 1])
            self.engine.state(self.rx)
            if self.engine.state is None:
                break

        self.engine.state(self.rx)

        self.assertEqual(self.engine.status_code, None)
        self.assertEqual(self.engine.state, self.engine._recv_payload_st)


class TestFileServingStateMachine(TestHttpBase):
    """
    Tests for file serving.
    """

    @classmethod
    def setUpClass(cls):
        cls.base_config = {
            "http_multipart": "False",
            # Only built-in file serving is tested here,
            # so disable /files endpoint to avoid conflicts
            "http_files_api": "False",
            "http_served_paths": "/www",
        }
        # Simplify file-open assertions by treating resources
        # as if they are installed at the root (/) rather than
        # relative to the current working directory.
        cls.cwd = "/"

    @staticmethod
    def patch_os_stat(stat_is_file=True):
        def patched(f):
            @patch("pyrobusta.protocol.http.stat", stat_factory(stat_is_file))
            def decorated(*args, **kwargs):
                return f(*args, **kwargs)

            return decorated

        return patched

    @patch_os_stat()
    def test_file_serving_root(self, *_):
        self.engine.url = b"/"
        self.engine.method = b"GET"
        self.engine.version = b"HTTP/1.1"
        self.engine.state = self.engine._fs_retrieve_st
        file_content = "index content"

        with patch("builtins.open", mock_open(read_data=file_content)) as m:
            self.engine.state(self.rx)
            m.assert_called_once_with("/www/index.html", "rb")

        self.assertEqual(self.engine.resp_handler.read(), file_content)
        self.assertEqual(self.engine.status_code, 200)
        self.assertEqual(self.engine.state, None)

    @patch_os_stat()
    def test_file_serving_subdir(self, *_):
        self.engine.url = b"/style/styles.css"
        self.engine.method = b"GET"
        self.engine.version = b"HTTP/1.1"
        self.engine.state = self.engine._fs_retrieve_st
        file_content = "/* Main styelsheet */"

        with patch("builtins.open", mock_open(read_data=file_content)) as m:
            self.engine.state(self.rx)
            m.assert_called_once_with("/www/style/styles.css", "rb")

        self.assertEqual(self.engine.resp_handler.read(), file_content)
        self.assertEqual(self.engine.status_code, 200)
        self.assertEqual(self.engine.state, None)

    @patch_os_stat()
    def test_file_serving_missing_file(self, *_):
        self.engine.url = b"/nonexistent.js"
        self.engine.method = b"GET"
        self.engine.version = b"HTTP/1.1"
        self.engine.state = self.engine._fs_retrieve_st

        self.engine.state(self.rx)

        self.assertEqual(self.engine.status_code, 404)
        self.assertEqual(self.engine.state, None)

    @patch_os_stat()
    def test_file_serving_known_content_type(self, *_):
        self.engine.url = b"/scripts.js"
        self.engine.method = b"GET"
        self.engine.version = b"HTTP/1.1"
        self.engine.state = self.engine._fs_retrieve_st
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
        self.engine.url = b"/scripts.unknown"
        self.engine.method = b"GET"
        self.engine.version = b"HTTP/1.1"
        self.engine.state = self.engine._fs_retrieve_st
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
