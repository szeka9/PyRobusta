"""
.env-style configuration reader,
Values can be encapsulated by single or double quotes.
"""

# pylint: disable = R0902,R0903

import gc

from pyrobusta import WORKING_DIR
from pyrobusta.utils.lexpath import normalize_path


class Config:
    """
    Configuration class with predefined defaults,
    configuration reader, and normalization method.
    """

    __slots__ = (
        "path",
        "wifi_ssid",
        "wifi_password",
        "tls",
        "tls_cert_file",
        "tls_key_file",
        "passwd_file",
        "roles_file",
        "log_level",
        "socket_max_con",
        "http_served_paths",
        "http_mem_cap",
        "http_port",
        "https_port",
        "http_multipart",
        "http_files_api",
        "http_auth",
        "http_browser_security",
        "http_insecure_auth",
        "http_sessions",
        "http_session_ttl_sec",
    )

    def __init__(self, path):
        self.path = path

        self.wifi_ssid = None
        self.wifi_password = None
        self.tls = False
        self.tls_cert_file = WORKING_DIR + "/cert.der"
        self.tls_key_file = WORKING_DIR + "/key.der"
        self.passwd_file = WORKING_DIR + "/pyrobusta.passwd"
        self.roles_file = WORKING_DIR + "/pyrobusta.roles"
        self.log_level = "info"
        self.socket_max_con = 2

        self.http_served_paths = ((WORKING_DIR + "/www"),)
        self.http_mem_cap = 0.1
        self.http_port = 80
        self.https_port = 443
        self.http_multipart = False
        self.http_files_api = False
        self.http_auth = None
        self.http_browser_security = True
        self.http_insecure_auth = False
        self.http_sessions = True
        self.http_session_ttl_sec = 900
        self._read()

    def _read(self):
        try:
            with open(self.path, encoding="utf-8") as conf:
                for line in conf:
                    line = line.rstrip("\r\n")
                    if not line:
                        continue
                    comment = line.find("#")
                    if comment >= 0:
                        line = line[:comment]
                    if not line.strip():
                        continue
                    key, value = line.split("=", 1)
                    key = key.strip().lower()
                    if key in self.__slots__:
                        value = value.strip()
                        if value[:1] in ("'", '"') and value[-1:] == value[:1]:
                            value = value[1:-1]
                        setattr(self, key, self._normalize(key, value))
                    gc.collect()
        except OSError:
            pass

    @staticmethod
    def _normalize(key, value):
        """
        Normalize a configuration value depending on the key.
        """
        if key in (
            "http_multipart",
            "http_files_api",
            "http_insecure_auth",
            "http_sessions",
            "http_browser_security",
            "tls",
        ):
            normalized = value.lower() == "true"
        elif key in (
            "http_port",
            "https_port",
            "socket_max_con",
            "http_session_ttl_sec",
        ):
            normalized = int(value)
        elif key == "http_mem_cap":
            normalized = float(value)
        elif key == "http_served_paths":
            normalized = tuple(normalize_path(p) for p in value.split())
        elif key in (
            "passwd_file",
            "roles_file",
            "tls_cert_file",
            "tls_key_file",
        ):
            normalized = normalize_path(value)
        elif key in ("wifi_ssid", "wifi_password"):
            normalized = value
        else:
            normalized = value.lower()
        return normalized
