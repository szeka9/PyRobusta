import subprocess
import tempfile
import socket
import time
import pathlib
import os
import shutil


class Server:
    def __init__(self, ip, http_port, https_port):
        try:
            socket.inet_aton(ip)
        except socket.error as exc:
            raise ValueError(f"Invalid device address: {self.device_ip}") from exc

        self.ip = ip
        self.http_port = http_port
        self.https_port = https_port
        self.config = {}

    def setup_config(self, **kwargs):
        self.config = dict(**kwargs)
        self.config["http_port"] = self.http_port
        self.config["https_port"] = self.https_port
        return "\n".join(f"{key}={value}" for key, value in self.config.items())

    def start(self, boot_script, healthcheck):
        raise RuntimeError("Not implemented")

    def terminate(self):
        raise RuntimeError("Not implemented")

    def read_file(self, file_path):
        raise RuntimeError("Not implemented")

    def write_file(self, file_path, content):
        raise RuntimeError("Not implemented")

    def mkdir(self, path: str):
        raise RuntimeError("Not implemented")

    def rmdir(self, path: str):
        raise RuntimeError("Not implemented")

    @property
    def url(self):
        if self.config.get("tls"):
            proto = "https"
            port = self.https_port
        else:
            proto = "http"
            port = self.http_port
        return f"{proto}://{self.ip}:{port}"

    def _wait_ready(self, timeout=30):
        deadline = time.monotonic() + timeout
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        while time.monotonic() < deadline:
            try:
                port = self.https_port if self.config.get("tls") else self.http_port
                s.connect((self.ip, int(port)))
                s.shutdown(2)
                return
            except ConnectionRefusedError:
                time.sleep(1)
                pass
        raise TimeoutError


class LocalServer(Server):
    def __init__(self, ip, server_directory, micropython_path):
        super().__init__(ip, 8080, 4443)
        self.directory = pathlib.Path(server_directory)
        self.micropython_path = micropython_path
        self.server_process = None

    def setup_config(self, **kwargs):
        with open(self.directory / "pyrobusta.env", "w") as config:
            config.write(super().setup_config(**kwargs))

    def start(self, boot_script, healthcheck=True):
        with open(self.directory / "boot.py", "w") as boot_file:
            boot_file.write(boot_script)

        if not "www" in os.listdir(self.directory):
            self.mkdir("/www")

        self.server_process = subprocess.Popen(
            [self.micropython_path, "boot.py"],
            cwd=self.directory,
            env={"MICROPYPATH": ":.frozen:lib"},
            stdout=subprocess.DEVNULL,
        )
        if healthcheck:
            self._wait_ready()

    def terminate(self):
        if self.server_process is not None:
            self.server_process.terminate()
            try:
                self.server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.server_process.kill()
                self.server_process.wait()

            self.server_process = None

    def read_file(self, file_path):
        with open(self.directory / file_path.lstrip("/")) as f:
            return f.read()

    def write_file(self, file_path, content):
        with open(self.directory / file_path.lstrip("/"), "w") as f:
            f.write(content)
        return str(self.directory / file_path.lstrip("/"))

    def mkdir(self, path: str):
        os.mkdir(self.directory / path.lstrip("/"))

    def rmdir(self, path: str):
        shutil.rmtree(self.directory / path.lstrip("/"))


class DeviceServer(Server):
    def __init__(self, ip, device_id):
        super().__init__(ip, 80, 443)
        self.device_id = device_id
        self.server_process = None

    def setup_config(self, **kwargs):
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

        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as config:
            config.write(super().setup_config(**kwargs))

            if (
                "wifi_ssid" not in current_config
                or "wifi_password" not in current_config
            ):
                print("Warning: Wi-Fi credentials are missing")
            else:
                config.write(f"\nwifi_ssid={current_config["wifi_ssid"]}")
                config.write(f"\nwifi_password={current_config["wifi_password"]}")
            config.flush()

            subprocess.run(
                ["mpremote", self.device_id, "cp", config.name, ":/pyrobusta.env"],
                check=True,
                stdout=subprocess.DEVNULL,
            )

    def start(self, boot_script, healthcheck=True):
        try:
            self.mkdir("/www")
        except subprocess.SubprocessError:
            pass

        fd, boot_path = tempfile.mkstemp(suffix=".py")
        os.close(fd)

        with open(boot_path, "w", encoding="utf-8") as boot:
            boot.write(boot_script)

        self.server_process = subprocess.Popen(
            ["mpremote", self.device_id, "run", boot_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        time.sleep(5)

        if healthcheck:
            self._wait_ready()

    def terminate(self):
        if self.server_process is not None:
            self.server_process.terminate()
            try:
                self.server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.server_process.kill()
                self.server_process.wait()

            self.server_process = None

        subprocess.run(["mpremote", self.device_id, "soft-reset"], check=True)
        time.sleep(2)

    def read_file(self, file_path):
        return subprocess.run(
            ["mpremote", self.device_id, "cat", f":{file_path}"],
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

    def mkdir(self, path: str):
        subprocess.run(
            ["mpremote", self.device_id, "mkdir", f":{path}"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def rmdir(self, path: str):
        script = f"""
import os

def rmtree(path):
    for name in os.listdir(path):
        child = path + "/" + name
        try:
            os.remove(child)
        except OSError:
            rmtree(child)
    os.rmdir(path)

rmtree({("/" + path)!r})
"""

        subprocess.run(
            ["mpremote", self.device_id, "exec", script],
            check=True,
        )
