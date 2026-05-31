import os
import unittest

from unittest import mock

from .http_base import TestHttpBase


class TestMultipartStateMachine(TestHttpBase):
    """
    Tests for multipart handling.
    """

    @classmethod
    def setUpClass(cls):
        cls.base_config = {"http_multipart": "True", "http_files_api": "False"}
        cls.cwd = os.getcwd()

    def test_multipart_parser(self):
        for case in [
            ({}, None),
            (
                {"content-type": 'multipart/form-data; boundary ="test-boundary"'},
                "test-boundary",
            ),
            (
                {"content-type": 'multipart/form-data; boundary =" test-boundary "'},
                " test-boundary ",
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
                self.assertEqual(self.engine._get_mp_boundary(case[0]), case[1])

        for case in [
            {"content-type": "multipart/form-data"},
            {"content-type": 'multipart/form-data;boundary=""'},
            {"content-type": "multipart/form-data;boundary=\r\n"},
            {"content-type": 'multipart/form-data;boundary="missing-quote'},
            {"content-type": 'multipart/form-data;boundary=missing-quote"'},
        ]:
            with self.subTest(headers=case):
                with self.assertRaises(self.http_module.InvalidHeaders):
                    self.engine._get_mp_boundary(case)

    def test_multipart_receiver_valid(self):
        self.engine.state = self.engine._start_multipart_parser_st
        self.engine.headers["content-length"] = 100
        self.engine.mp_boundary = b"test-boundary"
        body_part = b"--test-boundary\r\nContent-Type:text/plain"

        for i in range(len(body_part)):
            self.rx.write(body_part[i : i + 1])
            self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._parse_boundary_st)
        self.assertEqual(self.rx.peek(), b"Content-Type:text/plain")

    def test_multipart_receiver_boundary_mismatch(self):
        self.engine.state = self.engine._start_multipart_parser_st
        self.engine.version = b"HTTP/1.1"
        self.engine.headers["content-length"] = 100
        self.engine.mp_boundary = b"test-boundary"
        body_part = b"--test-boundary-delimiter\r\nContent-Type:text/plain"

        with self.assertRaises(self.http_module.MalformedRequest):
            for i in range(len(body_part)):
                self.rx.write(body_part[i : i + 1])
                self.engine.state(self.rx)

    def test_multipart_receiver_complete_part(self):
        self.engine.state = self.engine._parse_boundary_st
        self.engine.url = b"/api/test"
        self.engine.method = b"GET"

        test_callback = mock.Mock()
        self.engine.register("/api/test", test_callback)

        self.engine.headers["content-length"] = 1000
        self.engine.mp_boundary = b"test-boundary"
        self.engine.mp_delimiter = b"--test-boundary\r\n"
        self.engine.mp_last_delimiter = b"--test-boundary--"

        body_part = (
            b'Content-Disposition:form-data;name="file-chunk";filename="upload.txt"\r\n'
            b"Content-Type:text/plain\r\n\r\n"
            b"Upload content\r\n"
            b"--test-boundary\r\n"
        )

        for i in range(len(body_part)):
            self.assertEqual(self.engine.state, self.engine._parse_boundary_st)
            self.rx.write(body_part[i : i + 1])
            self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._parse_complete_part_st)
        self.assertEqual(self.rx.peek(), body_part)
        self.assertEqual(self.engine.mp_is_first, True)

        self.engine.state(self.rx)

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
        self.assertEqual(self.engine.mp_is_first, False)
        self.assertEqual(self.engine.mp_is_last, False)

    def test_multipart_receiver_last_part(self):
        self.engine.state = self.engine._parse_boundary_st
        self.engine.url = b"/api/test"
        self.engine.method = b"GET"
        self.engine.version = b"HTTP/1.1"
        self.engine.headers["content-length"] = 131
        self.engine.mp_boundary = b"test-boundary"
        self.engine.mp_delimiter = b"--test-boundary\r\n"
        self.engine.mp_last_delimiter = b"--test-boundary--"

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
            self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._parse_complete_part_st)
        self.assertEqual(self.rx.peek(), body_part)

        self.engine.state(self.rx)

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
        self.assertEqual(self.engine.mp_is_first, True)
        self.assertEqual(self.engine.mp_is_last, True)

    def test_multipart_content_length_match(self):
        self.engine.state = self.engine._start_multipart_parser_st
        self.engine.url = b"/api/test"
        self.engine.method = b"GET"
        self.engine.version = b"HTTP/1.1"
        self.engine.headers["content-length"] = 148
        self.engine.mp_boundary = b"test-boundary"

        test_callback = mock.Mock(return_value=("text/plain", "OK"))
        self.engine.register("/api/test", test_callback)

        body_part = (
            b"--test-boundary\r\n"
            b'Content-Disposition:form-data;name="file-chunk";filename="upload.txt"\r\n'
            b"Content-Type:text/plain\r\n\r\n"
            b"Upload content\r\n"
            b"--test-boundary--"
        )

        for i in range(len(body_part)):
            self.rx.write(body_part[i : i + 1])
            self.engine.state(self.rx)

        while self.engine.state is not None:
            self.engine.state(self.rx)

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

    def test_multipart_content_length_smaller(self):
        """
        Test if the engine correctly raises an error when content-length is
        smaller than actual payload length.
        """
        self.engine.state = self.engine._start_multipart_parser_st
        self.engine.url = b"/api/test"
        self.engine.method = b"GET"
        self.engine.version = b"HTTP/1.1"
        self.engine.headers["content-length"] = 148 - 1
        self.engine.mp_boundary = b"test-boundary"

        test_callback = mock.Mock(return_value=("text/plain", "OK"))
        self.engine.register("/api/test", test_callback)

        body_part = (
            b"--test-boundary\r\n"
            b'Content-Disposition:form-data;name="file-chunk";filename="upload.txt"\r\n'
            b"Content-Type:text/plain\r\n\r\n"
            b"Upload content\r\n"
            b"--test-boundary--"
        )

        for i in range(len(body_part)):
            self.rx.write(body_part[i : i + 1])
            self.engine.state(self.rx)

        with self.assertRaises(self.http_module.InvalidContentLength):
            while self.engine.state is not None:
                self.engine.state(self.rx)

    def test_multipart_content_length_larger(self):
        """
        Test if the engine correctly waits for remaining data when content-length is larger
        than actual payload length.
        """
        self.engine.state = self.engine._start_multipart_parser_st
        self.engine.url = b"/api/test"
        self.engine.method = b"GET"
        self.engine.version = b"HTTP/1.1"
        self.engine.headers["content-length"] = 148 + 1
        self.engine.mp_boundary = b"test-boundary"

        test_callback = mock.Mock(return_value=("text/plain", "OK"))
        self.engine.register("/api/test", test_callback)

        body_part = (
            b"--test-boundary\r\n"
            b'Content-Disposition:form-data;name="file-chunk";filename="upload.txt"\r\n'
            b"Content-Type:text/plain\r\n\r\n"
            b"Upload content\r\n"
            b"--test-boundary--"
        )

        for i in range(len(body_part)):
            self.rx.write(body_part[i : i + 1])
            self.engine.state(self.rx)

        self.engine.state(self.rx)

        self.assertEqual(self.engine.state, self.engine._parse_boundary_st)
        self.assertEqual(self.engine.status_code, None)

    def test_multipart_epilogue_data(self):
        """
        Test if the engine correctly raises an error when epilogue data
        is present after the last boundary delimiter.
        """
        self.engine.state = self.engine._start_multipart_parser_st
        self.engine.url = b"/api/test"
        self.engine.method = b"GET"
        self.engine.version = b"HTTP/1.1"
        self.engine.headers["content-length"] = 148 + 13
        self.engine.mp_boundary = b"test-boundary"

        test_callback = mock.Mock(return_value=("text/plain", "OK"))
        self.engine.register("/api/test", test_callback)

        body_part = (
            b"--test-boundary\r\n"
            b'Content-Disposition:form-data;name="file-chunk";filename="upload.txt"\r\n'
            b"Content-Type:text/plain\r\n\r\n"
            b"Upload content\r\n"
            b"--test-boundary--epilogue-data"
        )

        for i in range(len(body_part)):
            self.rx.write(body_part[i : i + 1])
            self.engine.state(self.rx)

        with self.assertRaises(self.http_module.InvalidContentLength):
            while self.engine.state is not None:
                self.engine.state(self.rx)

    def test_multipart_complete_part_trailing_crlf(self):
        self.engine.state = self.engine._start_multipart_parser_st
        self.engine.url = b"/api/test"
        self.engine.method = b"GET"
        self.engine.version = b"HTTP/1.1"
        self.engine.headers["content-length"] = 150
        self.engine.mp_boundary = b"test-boundary"

        test_callback = mock.Mock(return_value=("text/plain", "OK"))
        self.engine.register("/api/test", test_callback)

        body_part = (
            b"--test-boundary\r\n"
            b'Content-Disposition:form-data;name="file-chunk";filename="upload.txt"\r\n'
            b"Content-Type:text/plain\r\n\r\n"
            b"Upload content\r\n"
            b"--test-boundary--\r\n"
        )

        for i in range(len(body_part)):
            self.rx.write(body_part[i : i + 1])
            self.engine.state(self.rx)

        while self.engine.state is not None:
            self.engine.state(self.rx)

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
