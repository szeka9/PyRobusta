"""
.env-style configuration reader,
configuration is read from /pyrobusta.env.
Values can be encapsulated by single or double quotes.
"""

try:
    from micropython import const
except ImportError:

    def const(n):  # pylint: disable=C0116
        return n


from pyrobusta.utils.lexpath import normalize_path

PYROBUSTA_VERSION = "v0.8.0"
CONFIG_LOCATION = normalize_path("/pyrobusta.env")

# -------------------------------------------
# Global runtime configuration keys.
# Provide these keys when using get_config().
# -------------------------------------------
CONF_WIFI_SSID = const(0)
CONF_WIFI_PASSWORD = const(1)
CONF_HTTP_PORT = const(2)
CONF_HTTPS_PORT = const(3)
CONF_HTTP_MULTIPART = const(4)
CONF_HTTP_MEM_CAP = const(5)
CONF_HTTP_SERVED_PATHS = const(6)
CONF_HTTP_FILES_API = const(7)
CONF_HTTP_AUTH = const(8)
CONF_HTTP_AUTH_MODE = const(9)
CONF_HTTP_INSECURE_AUTH = const(10)
CONF_SOCKET_MAX_CON = const(11)
CONF_TLS = const(12)
CONF_TLS_CERT_FILE = const(13)
CONF_TLS_KEY_FILE = const(14)
CONF_PASSWD_FILE = const(15)
CONF_ROLES_FILE = const(16)
CONF_LOG_LEVEL = const(17)

# -------------------
# Configuration state
# -------------------
_CONFIG_LOADED = False
_CONFIG_CACHE = [
    None,  # CONF_WIFI_SSID
    None,  # CONF_WIFI_PASSWORD
    80,  # CONF_HTTP_PORT
    443,  # CONF_HTTPS_PORT
    False,  # CONF_HTTP_MULTIPART
    0.1,  # CONF_HTTP_MEM_CAP
    [
        normalize_path("/www"),
        normalize_path("/lib/pyrobusta"),
    ],  # CONF_HTTP_SERVED_PATHS
    False,  # CONF_HTTP_FILES_API
    None,  # CONF_HTTP_AUTH
    "browser",  # CONF_HTTP_AUTH
    False,  # CONF_HTTP_INSECURE_AUTH
    2,  # CONF_SOCKET_MAX_CON
    False,  # CONF_TLS
    normalize_path("/cert.der"),  # CONF_TLS_CERT_FILE
    normalize_path("/key.der"),  # CONF_TLS_KEY_FILE
    normalize_path("/pyrobusta.passwd"),  # CONF_PASSWD_FILE
    normalize_path("/pyrobusta.roles"),  # CONF_ROLES_FILE
    "info",  # CONF_LOG_LEVEL
]


# --------------
# Public helpers
# --------------
# pylint: disable=R0911
def parse_config(key, value):
    """
    Normalize a configuration value depending on the key.
    """
    if key in (
        CONF_HTTP_MULTIPART,
        CONF_HTTP_FILES_API,
        CONF_HTTP_INSECURE_AUTH,
        CONF_TLS,
    ):
        return value.lower() == "true"
    if key in (CONF_HTTP_PORT, CONF_HTTPS_PORT, CONF_SOCKET_MAX_CON):
        return int(value)
    if key == CONF_HTTP_MEM_CAP:
        return float(value)
    if key == CONF_HTTP_SERVED_PATHS:
        return [normalize_path(p) for p in value.split()]
    if key in (
        CONF_PASSWD_FILE,
        CONF_ROLES_FILE,
        CONF_TLS_CERT_FILE,
        CONF_TLS_KEY_FILE,
    ):
        return normalize_path(value)
    if key in (CONF_WIFI_SSID, CONF_WIFI_PASSWORD):
        return value
    return value.lower()


def read_config(config=CONFIG_LOCATION):
    """
    Read configuration from a file and update _CONFIG_CACHE.
    :param config: path to configuration.
    """
    try:
        with open(config, encoding="utf-8") as conf:
            for line in conf:
                line = line.rstrip("\r\n").split("#")[0]
                if not line.strip():
                    continue

                key_name, value = line.split("=", 1)
                key = globals().get("CONF_" + key_name.strip().upper())
                if key is None:
                    continue

                value = value.strip().strip("'").strip('"')
                _CONFIG_CACHE[key] = parse_config(key, value)

    except OSError:
        pass


def is_protected_file(norm_path: str):
    """
    Determines if a file path is required for core configuration
    and is not meant to be served or handled by the server.
    """
    return norm_path in (
        CONFIG_LOCATION,
        get_config(CONF_PASSWD_FILE),
        get_config(CONF_ROLES_FILE),
        get_config(CONF_TLS_CERT_FILE),
        get_config(CONF_TLS_KEY_FILE),
    )


def get_config(key):
    """
    Read configuration by key.
    The cache is reloaded during the first read.
    """
    global _CONFIG_LOADED  # pylint: disable=W0603
    if not _CONFIG_LOADED:
        read_config()
        _CONFIG_LOADED = True
    return _CONFIG_CACHE[key]
