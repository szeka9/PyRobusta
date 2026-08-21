import subprocess
import tempfile
import socket
import os
import time


class Device:
    def __init__(
        self,
        device_id: str,
        device_ip: str,
        device_name: str,
        base_config: dict,
        boot_script: str,
    ):
        self.device_id = device_id
        self.device_ip = device_ip
        self.device_name = device_name
        self.base_config = base_config
        self.boot_script = boot_script
        self.current_config = {}
        self.server_process = None

        self.validate_device_ip()

    def apply_config(self, config: dict):
        """
        Apply device configuration with mpremote
        """
        self.current_config = dict(config)

        subprocess.run(["mpremote", self.device_id, "soft-reset"], check=True)

        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as tmp:
            config_lines = subprocess.run(
                ["mpremote", self.device_id, "cat", ":/pyrobusta.env"],
                check=True,
                stdout=subprocess.PIPE,
                text=True,
            ).stdout.splitlines()

            current_config = {}

            for line in config_lines:
                line = line.rstrip("\r\n").split("#")[0]
                if not line.strip():
                    continue
                parts = line.split("=", 1)
                key = parts[0].strip()
                value = parts[1].strip().strip("'").strip('"')
                current_config[key] = value

            current_config.update(config)

            tmp.write(
                "\n".join([f"{key}={value}" for key, value in current_config.items()])
                + "\n"
            )
            tmp.flush()

            subprocess.run(
                ["mpremote", self.device_id, "cp", tmp.name, ":/pyrobusta.env"],
                check=True,
            )

        if config["http_auth"]:
            self.write_file(
                "/pyrobusta.passwd",
                "alice:role-1:mKmmf5wBEtlkty7LEcphieciOd3Pl0yY7r3WmDiZnzg=:XTQgg3Has79lDTNYVW+aPw=="
                ":5000:PBKDF2-HMAC-SHA256:v1.2.3\n",
            )
            self.write_file(
                "/pyrobusta.roles",
                "/\n/**\n*: role-1\n",
            )

        subprocess.run(["mpremote", self.device_id, "reset"], check=True)
        time.sleep(5)  # Allow the device to initialize

    def get_mem_params(self):
        """
        Determine SRAM and buffer settings of a device
        """
        sram_bytes = int(
            subprocess.run(
                [
                    "mpremote",
                    self.device_id,
                    "exec",
                    "import gc\nprint(gc.mem_free() + gc.mem_alloc())",
                ],
                check=True,
                stdout=subprocess.PIPE,
                text=True,
            ).stdout
        )

        (
            send_buf_min_bytes,
            send_buf_max_bytes,
            recv_buf_min_bytes,
            recv_buf_max_bytes,
            con_overhead,
        ) = [
            int(i)
            for i in subprocess.run(
                [
                    "mpremote",
                    self.device_id,
                    "exec",
                    (
                        "from pyrobusta.server.http_server import HttpServer\n"
                        "print( HttpServer.SEND_BUF_MIN_BYTES,\n"
                        "HttpServer.SEND_BUF_MAX_BYTES,\n"
                        "HttpServer.RECV_BUF_MIN_BYTES,\n"
                        "HttpServer.RECV_BUF_MAX_BYTES,\n"
                        "HttpServer.CON_OVERHEAD_BYTES,\n"
                        ")"
                    ),
                ],
                check=True,
                stdout=subprocess.PIPE,
                text=True,
            ).stdout.split()
        ]

        buffer_small = send_buf_min_bytes + recv_buf_min_bytes + con_overhead
        buffer_large = send_buf_max_bytes + recv_buf_max_bytes + con_overhead
        return sram_bytes, buffer_small, buffer_large

    def validate_device_ip(self):
        """
        Check if a device IP is valid
        """
        try:
            socket.inet_aton(self.device_ip)
        except socket.error as exc:
            raise ValueError(f"Invalid device address: {self.device_ip}") from exc

    def get_host(self):
        proto = "https" if self.current_config["tls"] else "http"
        port = 4443 if self.current_config["tls"] else 8080
        return f"{proto}://{self.device_ip}:{port}"

    def read_file(self, filename):
        return subprocess.run(
            ["mpremote", self.device_id, "cat", f":/{filename}"],
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        ).stdout

    def write_file(self, file_path, content):
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as file:
            file.write(content)
            file.flush()

            subprocess.run(
                ["mpremote", self.device_id, "cp", file.name, f":{file_path}"],
                check=True,
                stdout=subprocess.DEVNULL,
            )
        return f"{file_path}"

    def terminate(self):
        if self.server_process is not None:
            self.server_process.terminate()
            try:
                self.server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.server_process.kill()
                self.server_process.wait()

            self.server_process = None

    def run(self):
        app_script = ""

        with open("app_base.py") as app:
            app_script += "\n" + app.read()

        if self.current_config["http_multipart"]:
            with open("app_multipart.py") as o:
                app_script += "\n" + o.read()

        with open(self.boot_script) as b:
            content = b.read().replace("# <PLACEHOLDER>", app_script)

        fd, boot_path = tempfile.mkstemp(suffix=".py")
        os.close(fd)

        with open(boot_path, "w", encoding="utf-8") as boot:
            boot.write(content)

        self.server_process = subprocess.Popen(
            ["mpremote", self.device_id, "run", boot_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        self.boot_path = boot_path
