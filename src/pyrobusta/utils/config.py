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

PYROBUSTA_VERSION = "v0.4.0"
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
CONF_HTTP_SERVE_FILES = const(7)
CONF_SOCKET_MAX_CON = const(8)
CONF_TLS = const(9)
CONF_LOG_LEVEL = const(10)

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
    ["/www", "/lib/pyrobusta"],
    CONF_HTTP_SERVE_FILES,
    True,
    CONF_SOCKET_MAX_CON,
    2,
    CONF_TLS,
    False,
    CONF_LOG_LEVEL,
    "info",
]


# --------------
# Public helpers
# --------------
def parse_config(key, value):
    """
    Normalize a configuration value depending on the key.
    """
    if key in (CONF_HTTP_MULTIPART, CONF_HTTP_SERVE_FILES, CONF_TLS):
        return value.lower() == "true"
    if key in (CONF_HTTP_PORT, CONF_HTTPS_PORT, CONF_SOCKET_MAX_CON):
        return int(value)
    if key == CONF_HTTP_MEM_CAP:
        return float(value)
    if key == CONF_HTTP_SERVED_PATHS:
        return [normalize_path(p) for p in value.split()]
    if key not in (CONF_WIFI_SSID, CONF_WIFI_PASSWORD):
        return value.lower()
    return value


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
    The cache is reloaded if the key is missing
    or the value is set to None.
    """
    global _CONFIG_LOADED  # pylint: disable=W0603
    if _CONFIG_CACHE[2 * key + 1] is None or not _CONFIG_LOADED:
        read_config()
        _CONFIG_LOADED = True
    return _CONFIG_CACHE[2 * key + 1]
