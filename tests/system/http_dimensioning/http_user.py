from locust import HttpUser, task, constant

TLS_VERIFY = False


class DefaultUser(HttpUser):
    """
    Use the /index.html and /examples.html
    routes to test static file serving.
    """

    wait_time = constant(0)

    def on_start(self):
        self.client.verify = TLS_VERIFY

    @task(2)
    def get_index(self):
        response = self.client.get(
            "/index.html",
            name="/index.html",
        )
        print(
            self.client.base_url + "/index.html",
            response.status_code,
            response.elapsed.total_seconds(),
        )

    @task(2)
    def get_docs(self):
        response = self.client.get(
            "/examples.html",
            name="/examples.html",
        )
        print(
            self.client.base_url + "/examples.html",
            response.status_code,
            response.elapsed.total_seconds(),
        )

    @task(1)
    def post_chunked(self):
        """
        Use the /test/stream route to test chunked request handling,
        sending a chunked request with multiple chunks of specified size.
        """
        part_count = 10
        part_size = 256
        chunked_data = b""
        for i in range(part_count):
            chunked_data += b"%X\r\n" % part_size
            chunked_data += b"X" * part_size + b"\r\n"
        chunked_data += b"0\r\n\r\n"

        response = self.client.post(
            "/test/stream",
            data=chunked_data,
            headers={
                "Content-Type": "application/octet-stream",
                "Transfer-Encoding": "chunked",
            },
            name="/test/stream",
        )
        print(
            self.client.base_url
            + "/test/stream (chunked; parts=%d, size=%d)" % (part_count, part_size),
            response.status_code,
            response.elapsed.total_seconds(),
        )


class MultipartUser(HttpUser):
    wait_time = constant(0)

    def on_start(self):
        self.client.verify = TLS_VERIFY

    @task(2)
    def get_multipart(self):
        """
        Use the /test/multipart route with the x-part-count and x-part-size
        headers to test multipart response handling.
        """
        part_count = 10
        part_size = 256
        response = self.client.get(
            "/test/multipart",
            headers={"x-part-count": str(part_count), "x-part-size": str(part_size)},
            name="/test/multipart",
        )
        print(
            self.client.base_url
            + "/test/multipart (parts=%d, size=%d)" % (part_count, part_size),
            response.status_code,
            response.elapsed.total_seconds(),
        )

    @task(1)
    def post_multipart(self):
        """
        Use the /test/multipart route to test multipart request handling,
        sending multipart requests with multiple parts of specified size.
        """
        part_count = 10
        part_size = 256
        multipart_data = b""
        for i in range(part_count):
            multipart_data += b"--boundary\r\n"
            multipart_data += (
                b'Content-Disposition: form-data; name="part"; filename="part%d.txt"\r\n'
                % i
            )
            multipart_data += b"Content-Type: text/plain\r\n\r\n"
            multipart_data += b"X" * part_size + b"\r\n"
        multipart_data += b"--boundary--\r\n"

        response = self.client.post(
            "/test/multipart",
            data=multipart_data,
            headers={"Content-Type": "multipart/form-data; boundary=boundary"},
            name="/test/multipart",
        )
        print(
            self.client.base_url
            + "/test/multipart (multipart; parts=%d, size=%d)"
            % (part_count, part_size),
            response.status_code,
            response.elapsed.total_seconds(),
        )


class FilesApiUser(HttpUser):
    """
    Use the /files API to test static
    file serving with directory listing.
    """

    wait_time = constant(0)

    def on_start(self):
        self.client.verify = TLS_VERIFY

    @task(2)
    def get_index(self):
        response = self.client.get(
            "/files/www/index.html",
            name="/files/www/index.html",
        )
        print(
            self.client.base_url + "/files/www/index.html",
            response.status_code,
            response.elapsed.total_seconds(),
        )

    @task(2)
    def get_dir(self):
        response = self.client.get(
            "/files/www/",
            name="/files/www/",
        )
        print(
            self.client.base_url + "/files/www/",
            response.status_code,
            response.elapsed.total_seconds(),
        )
