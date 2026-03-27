import sys
import unittest
from unittest import mock
from unittest.mock import MagicMock, patch

from .utils import load_module


class TestWebStateMachineBase(unittest.TestCase):
    """
    Base class for stat machine tests.
    """

    @classmethod
    def setUpClass(cls):
        cls.config = {}

    def setUp(self):
        # Create mock modules
        self.mock_utils = MagicMock()
        self.mock_utils_config = MagicMock()
        self.mock_utils_config.get_config = MagicMock()
        self.mock_utils.config = self.mock_utils_config

        self.patcher = patch.dict(
            sys.modules,
            {
                "pyrobusta.utils": self.mock_utils,
                "pyrobusta.utils.config": self.mock_utils_config,
            },
        )
        self.patcher.start()

        for key, value in self.config.items():
            self.set_mock_config(key, value)

        # Load your web and buffer modules
        buffer_module = load_module("pyrobusta/stream/buffer.py")
        web_module = load_module("pyrobusta/protocol/http.py")
        web_module.enable_optional_features()

        self.engine = web_module.HttpEngine()
        self.rx = buffer_module.SlidingBuffer(bytearray(1024))
        self.tx = buffer_module.SlidingBuffer(bytearray(1024))

    def tearDown(self):
        self.patcher.stop()

    def set_mock_config(self, key, value):
        def side_effect(input_arg, *_, **__):
            if input_arg == key:
                return value
            raise ValueError(f"Unexpected argument: {input_arg}")

        self.mock_utils_config.get_config.side_effect = side_effect


class TestWebStateMachine(TestWebStateMachineBase):
    """
    Tests for the core functionality of the state machine.
    """

    @classmethod
    def setUpClass(cls):
        cls.config = {"http_multipart": "False"}

    def test_status_parsing_valid(self):
        request = b"GET /index.html HTTP/1.1\r\nContent-Length:10"

        for i in range(len(request)):
            self.rx.write(request[i : i + 1])
            self.engine.state(self.rx, self.tx)

        self.assertEqual(self.engine.method, b"GET")
        self.assertEqual(self.engine.url, b"/index.html")
        self.assertEqual(self.engine.version, b"HTTP/1.1")
        self.assertEqual(self.rx.peek(), b"Content-Length:10")
        self.assertEqual(self.engine.state, self.engine._parse_headers_st)

    def test_status_parsing_incomplete_line(self):
        request = b"GET /index.html HTTP/1.1"

        for i in range(len(request)):
            self.rx.write(request[i : i + 1])
            self.engine.state(self.rx, self.tx)
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
            self.engine.state(self.rx, self.tx)
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
            self.engine.state(self.rx, self.tx)
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
            self.engine.state(self.rx, self.tx)

        self.assertDictEqual(
            {"content-length": 10, "content-type": "application/json"},
            self.engine.headers,
        )
        self.assertEqual(self.rx.peek(), b"")
        self.assertEqual(self.engine.state, self.engine._route_request_st)

    def test_header_parsing_incomplete_header(self):
        request = b"GET /index.html HTTP/1.1\r\nContent-Type\r\n\r\n"

        for i in range(len(request)):
            self.rx.write(request[i : i + 1])
            self.engine.state(self.rx, self.tx)
            if self.engine.state is None:
                break

        self.assertEqual(self.engine.status_code, 400)
        self.assertEqual(self.engine.state, None)

    def test_routing_unsupported_method(self):
        self.engine.state = self.engine._route_request_st
        self.engine.url = b"/api/test"
        self.engine.method = b"GET"
        self.engine.version = b"HTTP/1.1"

        test_callback = mock.Mock()
        self.engine.register("/api/test", test_callback, "POST")

        self.engine.state(self.rx, self.tx)

        self.assertEqual(self.engine.status_code, 405)
        self.assertEqual(self.engine.state, None)
        self.assertIn(b"allow", self.engine.response_headers)
        self.assertIn(b"POST", self.engine.response_headers)

    def test_routing_options_method(self):
        self.engine.state = self.engine._route_request_st
        self.engine.url = b"/api/test"
        self.engine.method = b"OPTIONS"
        self.engine.version = b"HTTP/1.1"

        test_callback = mock.Mock()
        self.engine.register("/api/test", test_callback, "GET")
        self.engine.register("/api/test", test_callback, "POST")
        self.engine.register("/api/test", test_callback, "PUT")

        self.engine.state(self.rx, self.tx)

        self.assertEqual(self.engine.status_code, 204)
        self.assertEqual(self.engine.state, None)
        self.assertIn(b"allow", self.engine.response_headers)
        self.assertIn(b"GET, POST, PUT", self.engine.response_headers)

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
            self.engine.state(self.rx, self.tx)

        self.assertEqual(self.engine.status_code, 200)
        self.assertEqual(self.engine.state, None)
        self.assertNotEqual(
            self.tx.find(b"content-length: " + str(len(test_response)).encode("ascii")),
            -1,
        )
        self.assertNotEqual(self.tx.find(test_response), -1)

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
            self.engine.state(self.rx, self.tx)

        self.assertEqual(self.engine.status_code, 200)
        self.assertEqual(self.engine.state, None)
        self.assertNotEqual(
            self.tx.find(b"content-length: " + str(len(test_response)).encode("ascii")),
            -1,
        )
        self.assertEqual(self.tx.find(test_response), -1)

    def test_simple_query_parameter(self):
        request = b"GET /api/test?param HTTP/1.1\r\n"

        for i in range(len(request)):
            self.rx.write(request[i : i + 1])
            self.engine.state(self.rx, self.tx)

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
            self.engine.state(self.rx, self.tx)

        self.assertEqual(self.engine.query, f"safe_chars.{unsafe_chars}")

    def test_single_url_encoded_query_parameter(self):
        request = b"GET /api/test?param=value HTTP/1.1\r\n"

        for i in range(len(request)):
            self.rx.write(request[i : i + 1])
            self.engine.state(self.rx, self.tx)

        self.assertEqual(
            self.engine.get_url_encoded_query_param(self.engine.query, "param"), "value"
        )

    def test_multiple_url_encoded_query_parameter(self):
        request = (
            b"GET /api/test?param1=value1&param2=value2&param3=value3 HTTP/1.1\r\n"
        )

        for i in range(len(request)):
            self.rx.write(request[i : i + 1])
            self.engine.state(self.rx, self.tx)

        self.assertEqual(
            self.engine.get_url_encoded_query_param(self.engine.query, "param1"),
            "value1",
        )
        self.assertEqual(
            self.engine.get_url_encoded_query_param(self.engine.query, "param2"),
            "value2",
        )
        self.assertEqual(
            self.engine.get_url_encoded_query_param(self.engine.query, "param3"),
            "value3",
        )

    def test_empty_or_missing_url_encoded_query_parameter(self):
        request = (
            b"GET /api/test?param1=&param2= HTTP/1.1\r\n"
        )

        for i in range(len(request)):
            self.rx.write(request[i : i + 1])
            self.engine.state(self.rx, self.tx)

        self.assertEqual(
            self.engine.get_url_encoded_query_param(self.engine.query, "param1"),
            "",
        )
        self.assertEqual(
            self.engine.get_url_encoded_query_param(self.engine.query, "param2"),
            "",
        )
        self.assertEqual(
            self.engine.get_url_encoded_query_param(self.engine.query, "param3", "default"),
            "default",
        )

        with self.assertRaises(KeyError):
            self.engine.get_url_encoded_query_param(self.engine.query, "param3")


class TestMultipartStateMachine(TestWebStateMachineBase):
    """
    Tests for multipart handling
    """

    @classmethod
    def setUpClass(cls):
        cls.config = {"http_multipart": "True"}

    def test_multipart_parser(self):
        for case in [
            (
                {"content-type": 'multipart/form-data; boundary ="test-boundary"'},
                "test-boundary",
            ),
            (
                {"content-type": "multipart/form-data ;boundary= test-boundary "},
                "test-boundary",
            ),
            (
                {"content-type": "multipart/form-data;boundary=a test boundary "},
                "a test boundary",
            ),
        ]:
            with self.subTest(headers=case[0], expected=case[1]):
                self.assertEqual(self.engine._is_multipart(case[0]), case[1])

        for case in [
            {},
            {"content-type": "multipart/form-data"},
            {"content-type": 'multipart/form-data;boundary=""'},
            {"content-type": "multipart/form-data;boundary=\r\n"},
        ]:
            with self.subTest(headers=case, expected=None):
                self.assertEqual(self.engine._is_multipart(case), None)

    def test_multipart_receiver_valid(self):
        self.engine.state = self.engine._start_multipart_parser_st
        self.engine.headers["content-length"] = 100
        self.engine.mp_boundary = b"test-boundary"
        body_part = b"--test-boundary\r\nContent-Type:text/plain"

        for i in range(len(body_part)):
            self.rx.write(body_part[i : i + 1])
            self.engine.state(self.rx, self.tx)

        self.assertEqual(self.engine.state, self.engine._parse_boundary_st)
        self.assertEqual(self.rx.peek(), b"Content-Type:text/plain")

    def test_multipart_receiver_boundary_mismatch(self):
        self.engine.state = self.engine._start_multipart_parser_st
        self.engine.version = b"HTTP/1.1"
        self.engine.headers["content-length"] = 100
        self.engine.mp_boundary = b"test-boundary"
        body_part = b"--test-boundary-delimiter\r\nContent-Type:text/plain"

        for i in range(len(body_part)):
            self.rx.write(body_part[i : i + 1])
            self.engine.state(self.rx, self.tx)
            if self.engine.state is None:
                break

        self.assertEqual(self.engine.state, None)
        self.assertEqual(self.engine.status_code, 400)
        self.assertEqual(self.rx.peek(), b"--test-boundary-delimiter\r\n")

    def test_multipart_receiver_complete_part(self):
        self.engine.state = self.engine._parse_boundary_st
        self.engine.url = b"/api/test"
        self.engine.method = b"GET"

        test_callback = mock.Mock()
        self.engine.register("/api/test", test_callback)

        self.engine.headers["content-length"] = 1000
        self.engine.mp_boundary = b"test-boundary"
        self.engine.mp_delimiter = b"--test-boundary\r\n"
        self.engine.mp_closing_delimiter = b"--test-boundary--"

        body_part = (
            b'Content-Disposition:form-data;name="file-chunk";filename="upload.txt"\r\n'
            b"Content-Type:text/plain\r\n\r\n"
            b"Upload content\r\n"
            b"--test-boundary\r\n"
        )

        for i in range(len(body_part)):
            self.assertEqual(self.engine.state, self.engine._parse_boundary_st)
            self.rx.write(body_part[i : i + 1])
            self.engine.state(self.rx, self.tx)

        self.assertEqual(self.engine.state, self.engine._parse_complete_part_st)
        self.assertEqual(self.rx.peek(), body_part)
        self.assertEqual(self.engine.mp_first_part, True)

        self.engine.state(self.rx, self.tx)

        self.assertEqual(self.engine.state, self.engine._parse_boundary_st)
        test_callback.assert_called_once_with(
            self.engine,
            (
                {
                    "content-disposition": 'form-data;name="file-chunk";filename="upload.txt"',
                    "content-type": "text/plain",
                },
                b"Upload content",
            ),
        )
        self.assertEqual(self.engine.mp_first_part, False)
        self.assertEqual(self.engine.mp_last_part, False)

    def test_multipart_receiver_last_part(self):
        self.engine.state = self.engine._parse_boundary_st
        self.engine.url = b"/api/test"
        self.engine.method = b"GET"
        self.engine.version = b"HTTP/1.1"
        self.engine.headers["content-length"] = 131
        self.engine.mp_boundary = b"test-boundary"
        self.engine.mp_delimiter = b"--test-boundary\r\n"
        self.engine.mp_closing_delimiter = b"--test-boundary--"

        test_callback = mock.Mock(return_value=("text/plain", "OK"))
        self.engine.register("/api/test", test_callback)

        body_part = (
            b'Content-Disposition:form-data;name="file-chunk";filename="upload.txt"\r\n'
            b"Content-Type:text/plain\r\n\r\n"
            b"Upload content\r\n"
            b"--test-boundary--"
        )

        for i in range(len(body_part)):
            self.assertEqual(self.engine.state, self.engine._parse_boundary_st)
            self.rx.write(body_part[i : i + 1])
            self.engine.state(self.rx, self.tx)

        self.assertEqual(self.engine.state, self.engine._parse_complete_part_st)
        self.assertEqual(self.rx.peek(), body_part)

        self.engine.state(self.rx, self.tx)

        self.assertEqual(self.engine.state, None)
        self.assertEqual(self.engine.status_code, 200)
        test_callback.assert_called_once_with(
            self.engine,
            (
                {
                    "content-disposition": 'form-data;name="file-chunk";filename="upload.txt"',
                    "content-type": "text/plain",
                },
                b"Upload content",
            ),
        )
        self.assertEqual(self.engine.mp_first_part, True)
        self.assertEqual(self.engine.mp_last_part, True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
