from locust import HttpUser, task, constant

TLS_VERIFY = False
AUTH = None  # ("username", "password")


class DefaultTasks:
    """
    Traffic operations for the default/static + chunked profile.
    """

    def get_index(self, client):
        response = client.get(
            "/index.html",
            name="/index.html",
            auth=AUTH,
        )
        print(
            client.base_url + "/index.html",
            response.status_code,
            response.elapsed.total_seconds(),
        )

    def post_chunked(self, client):
        """
        Use /test/stream to test chunked request handling.
        """
        part_count = 10
        part_size = 256

        chunked_data = b""
        for _ in range(part_count):
            chunked_data += b"%X\r\n" % part_size
            chunked_data += b"X" * part_size + b"\r\n"
        chunked_data += b"0\r\n\r\n"

        response = client.post(
            "/test/stream",
            data=chunked_data,
            headers={
                "Content-Type": "application/octet-stream",
                "Transfer-Encoding": "chunked",
            },
            name="/test/stream",
            auth=AUTH,
        )
        print(
            client.base_url
            + f"/test/stream (chunked; parts={part_count}, size={part_size})",
            response.status_code,
            response.elapsed.total_seconds(),
        )


class MultipartTasks:
    """
    Traffic operations for multipart request/response testing.
    """

    def get_multipart(self, client):
        """
        Use /test/multipart to test multipart response handling.
        """
        part_count = 10
        part_size = 256

        response = client.get(
            "/test/multipart",
            headers={
                "x-part-count": str(part_count),
                "x-part-size": str(part_size),
            },
            name="/test/multipart",
            auth=AUTH,
        )
        print(
            client.base_url + f"/test/multipart (parts={part_count}, size={part_size})",
            response.status_code,
            response.elapsed.total_seconds(),
        )

    def post_multipart(self, client):
        """
        Use /test/multipart to test multipart request handling.
        """
        part_count = 10
        part_size = 256

        multipart_data = b""

        for i in range(part_count):
            multipart_data += b"--boundary\r\n"
            multipart_data += (
                b'Content-Disposition: form-data; name="part"; '
                b'filename="part%d.txt"\r\n' % i
            )
            multipart_data += b"Content-Type: text/plain\r\n\r\n"
            multipart_data += b"X" * part_size + b"\r\n"

        multipart_data += b"--boundary--\r\n"

        response = client.post(
            "/test/multipart",
            data=multipart_data,
            headers={
                "Content-Type": "multipart/form-data; boundary=boundary",
            },
            name="/test/multipart",
            auth=AUTH,
        )
        print(
            client.base_url
            + f"/test/multipart (multipart; parts={part_count}, size={part_size})",
            response.status_code,
            response.elapsed.total_seconds(),
        )


class FilesApiTasks:
    """
    Traffic operations for the /files API.
    """

    def get_files_index(self, client):
        response = client.get(
            "/files/www/index.html",
            name="/files/www/index.html",
            auth=AUTH,
        )
        print(
            client.base_url + "/files/www/index.html",
            response.status_code,
            response.elapsed.total_seconds(),
        )

    def get_dir(self, client):
        response = client.get(
            "/files/www/",
            name="/files/www/",
            auth=AUTH,
        )
        print(
            client.base_url + "/files/www/",
            response.status_code,
            response.elapsed.total_seconds(),
        )


class DefaultUser(DefaultTasks, HttpUser):
    """
    Use /index.html and /test/stream routes.
    """

    wait_time = constant(0)

    @task(4)
    def get_index_task(self):
        return self.get_index(self.client)

    @task(1)
    def post_chunked_task(self):
        return self.post_chunked(self.client)

    def on_start(self):
        self.client.verify = TLS_VERIFY


class MultipartUser(MultipartTasks, HttpUser):
    """
    Use /test/multipart routes.
    """

    wait_time = constant(0)

    @task(2)
    def get_multipart_task(self):
        return self.get_multipart(self.client)

    @task(1)
    def post_multipart_task(self):
        return self.post_multipart(self.client)

    def on_start(self):
        self.client.verify = TLS_VERIFY


class FilesApiUser(FilesApiTasks, HttpUser):
    """
    Use /files API routes.
    """

    wait_time = constant(0)

    @task(2)
    def get_files_index_task(self):
        return self.get_files_index(self.client)

    @task(2)
    def get_dir_task(self):
        return self.get_dir(self.client)

    def on_start(self):
        self.client.verify = TLS_VERIFY


class CompositeUser(
    DefaultTasks,
    MultipartTasks,
    FilesApiTasks,
    HttpUser,
):
    wait_time = constant(0)

    def on_start(self):
        self.client.verify = TLS_VERIFY

    @task(4)
    def get_index_task(self):
        return self.get_index(self.client)

    @task(1)
    def post_chunked_task(self):
        return self.post_chunked(self.client)

    @task(2)
    def get_multipart_task(self):
        return self.get_multipart(self.client)

    @task(1)
    def post_multipart_task(self):
        return self.post_multipart(self.client)

    @task(2)
    def get_files_index_task(self):
        return self.get_files_index(self.client)

    @task(2)
    def get_dir_task(self):
        return self.get_dir(self.client)
