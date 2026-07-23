# Configuration

[← Back](index.md)

This page documents PyRobusta configuration options,
configuration deployment using `mpremote`,
and runtime access to configuration values through the
configuration API.

---

## Table of Contents

* [Configuration](#configuration)
  + [Configuration Format & Deployment](#configuration-format-deployment)
  + [Parameter Description](#parameter-description)
  + [Configuration API](#configuration-api)

---

## Configuration Format & Deployment

Configuration overrides can be provided through `pyrobusta.env`, using standard `.env` syntax.
`pyrobusta.env` must be stored in the server root. Inline comments are supported using `#`.

```
# /pyrobusta.env - Example configuration

socket_max_con=2        # allow two simultaneous socket connections
http_multipart=False    # turn off multipart parser to lower heap usage
http_mem_cap=0.05       # limit heap usage of stream buffers to 5% of the total heap
tls=False               # turn off TLS
```

Perform a soft reset and upload `pyrobusta.env` using mpremote.

```
$ mpremote a0 soft-reset
$ mpremote a0 cp pyrobusta.env :/pyrobusta.env
```

## Parameter Description

| Name | Description | Default |
| --- | --- | --- |
| `wifi_ssid` | Name of the Wi-Fi network. When empty, Wi-Fi is not initialized by the built-in `wifi.py` module. | None |
| `wifi_password` | Password of the Wi-Fi network. When empty, Wi-Fi is not initialized by the built-in `wifi.py` module. | None |
| `http_port` | Port number for HTTP. | 80 |
| `https_port` | Port number for HTTPS. | 443 |
| `http_multipart` | Enables or disables multipart request and response processing. Enabling multipart support increases memory usage. | False |
| `http_mem_cap` | Fraction of available heap memory reserved for stream buffers. Valid range: (0, 1]. | 0.1 |
| `http_served_paths` | Space-separated list of filesystem paths that may be served over HTTP. | `/www /lib/pyrobusta` |
| `http_files_api` | Enables or disables the file management API endpoint (`/files`), allowing upload, download, and listing of files. | False |
| `http_auth` | Selects the type of authentication method enforced by the server. Currently, basic authentication (`basic`) is supported. | None |
| `socket_max_con` | Maximum number of simultaneous socket connections. | 2 |
| `tls` | Enables or disables TLS. When enabled, `cert.der` and `key.der` must be installed at the server root. | False |
| `log_level` | Logging level. Can be one of: `warning`, `info`, `debug`. | info |

## Configuration API

Configuration values can be accessed through the
`pyrobusta.utils.config` module.
Values are loaded from `pyrobusta.env` during server initialization.
Configuration values can be retrieved using
`get_config()` together with one of the
predefined `CONF_*` constants.

After initialization, configuration values are retrieved from an internal cache.
The cached values are normalized to their expected runtime types to avoid repeated
parsing of environment strings.

Configuration values are treated as immutable during runtime.
Changes are applied only when the configuration cache is reloaded.
The configuration cache can be reloaded by calling
`read_config()`, which re-reads `pyrobusta.env`
and rebuilds the internal normalized cache.

```
from pyrobusta.utils.config import get_config, CONF_TLS

@HttpEngine.route("/tls", "GET")
def tls_status(http_ctx, _):
    enabled = get_config(CONF_TLS)
    return "text/plain", f"TLS enabled: {enabled}"
```

---

PyRobusta v0.8.0 Web Server
