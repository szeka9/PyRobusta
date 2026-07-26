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


from .helpers import normalize_path

PYROBUSTA_VERSION = "v0.8.0"
CONFIG_LOCATION = "pyrobusta.env"

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
CONF_LOG_LEVEL = const(13)
CONF_PASSWD_FILE = const(14)
CONF_ROLES_FILE = const(15)

# -------------------
# Configuration state
# -------------------
_CONFIG_LOADED = False
_CONFIG_CACHE = [
    CONF_WIFI_SSID,
    None,
    CONF_WIFI_PASSWORD,
    None,
    CONF_HTTP_PORT,
    80,
    CONF_HTTPS_PORT,
    443,
    CONF_HTTP_MULTIPART,
    False,
    CONF_HTTP_MEM_CAP,
    0.1,
    CONF_HTTP_SERVED_PATHS,
    [normalize_path("/www"), normalize_path("/lib/pyrobusta")],
    CONF_HTTP_FILES_API,
    False,
    CONF_HTTP_AUTH,
    None,
    CONF_HTTP_AUTH_MODE,
    "browser",
    CONF_HTTP_INSECURE_AUTH,
    False,
    CONF_SOCKET_MAX_CON,
    2,
    CONF_TLS,
    False,
    CONF_LOG_LEVEL,
    "info",
    CONF_PASSWD_FILE,
    normalize_path("/pyrobusta.passwd"),
    CONF_ROLES_FILE,
    normalize_path("/pyrobusta.roles"),
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
    if key in (CONF_PASSWD_FILE, CONF_ROLES_FILE):
        return normalize_path(value)
    if key in (CONF_WIFI_SSID, CONF_WIFI_PASSWORD):
        return value
    return value.lower()


def read_config(config=CONFIG_LOCATION):
    """
    Read configuration from a file and update CONFIG_CACHE.
    :param config: path to configuration
    """
    try:
        with open(config, encoding="utf-8") as conf:
            for line in conf:
                line = line.rstrip("\r\n").split("#")[0]
                if not line.strip():
                    continue
                parts = line.split("=")
                key_name = "CONF_" + parts[0].strip().upper()
                if key_name in globals():
                    key = globals()[key_name]
                else:
                    key = len(_CONFIG_CACHE) // 2 + 1
                    globals()[key_name] = key
                value = parts[1].strip().strip("'").strip('"')
                value = parse_config(key, value)
                if (
                    key in _CONFIG_CACHE
                    and (conf_idx := _CONFIG_CACHE.index(key)) % 2 == 0
                ):
                    _CONFIG_CACHE[conf_idx + 1] = value
                else:
                    _CONFIG_CACHE.append(key)
                    _CONFIG_CACHE.append(value)
    except OSError:
        pass


def get_config(key):
    """
    Read configuration by key.
    The cache is reloaded during the first read.
    """
    global _CONFIG_LOADED  # pylint: disable=W0603
    if not _CONFIG_LOADED:
        read_config()
        _CONFIG_LOADED = True
    return _CONFIG_CACHE[2 * key + 1]
