CONFIG_LOCATION = "pyrobusta.env"
CONFIG_CACHE = [
    "wifi_ssid",
    None,
    "wifi_password",
    None,
    "http_multipart",
    None,
    "http_mem_cap",
    None,
    "socket_max_con",
    None,
]


def read_config(config=CONFIG_LOCATION):
    with open(config) as conf:
        for line in conf.read().splitlines("\n"):
            key = line.split("=")[0].strip()
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


def get_config(key):
    if key not in CONFIG_CACHE:
        read_config()
    try:
        conf_idx = CONFIG_CACHE.index(key)
    except IndexError:
        return None
    if CONFIG_CACHE[conf_idx + 1] is None:
        read_config()
        conf_idx = CONFIG_CACHE.index(key)
    return CONFIG_CACHE[conf_idx + 1]
