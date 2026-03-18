"""
.env-style configuration reader,
configuration is read from /pyrobusta.env.
Values can be encapsulated by single or double quotes.
"""

CONFIG_LOADED = False
CONFIG_LOCATION = "pyrobusta.env"
CONFIG_CACHE = [
    "wifi_ssid",
    None,
    "wifi_password",
    None,
    "http_multipart",
    "False",
    "http_mem_cap",
    0.1,
    "socket_max_con",
    2,
]


def read_config(config=CONFIG_LOCATION):
    """
    Read configuration from a file and update CONFIG_CACHE.
    :param config: path to configuration
    """
    try:
        with open(config, encoding="utf-8") as conf:
            for line in conf.read().splitlines("\n"):
                key = line.split("=")[0].strip()
                if key.startswith("#"):
                    continue
                value = line.split("=")[1].strip().strip("'").strip('"')
                if key and value:
                    if (
                        key in CONFIG_CACHE
                        and (conf_idx := CONFIG_CACHE.index(key)) % 2 == 0
                    ):
                        CONFIG_CACHE[conf_idx + 1] = value
                    else:
                        CONFIG_CACHE.append(key)
                        CONFIG_CACHE.append(value)
    except OSError:
        pass


def get_config(key):
    """
    Read configuration by key.
    The cache is reloaded if the key is missing
    or the value is set to None.
    """
    global CONFIG_LOADED  # pylint: disable=W0603
    if key not in CONFIG_CACHE or not CONFIG_LOADED:
        read_config()
        CONFIG_LOADED = True
    try:
        conf_idx = CONFIG_CACHE.index(key)
    except IndexError:
        return None
    if CONFIG_CACHE[conf_idx + 1] is None:
        read_config()
        conf_idx = CONFIG_CACHE.index(key)
    return CONFIG_CACHE[conf_idx + 1]
