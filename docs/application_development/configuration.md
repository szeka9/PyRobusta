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
  + [Configuration Loading](#configuration-loading)

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
$ mpremote connect /dev/ttyACM1 soft-reset
$ mpremote connect /dev/ttyACM1 cp pyrobusta.env :/pyrobusta.env
```

## Parameter Description

| Name | Description | Default |
| --- | --- | --- |
| `wifi_ssid` | Name of the Wi-Fi network. When empty, Wi-Fi is not initialized by the built-in `wifi.py` module. | None |
| `wifi_password` | Password of the Wi-Fi network. | None |
| `tls` | Enables or disables TLS. When enabled, `cert.der` and `key.der` must be installed at the server root. | False |
| `tls_cert_file` | Alternative path to the TLS certificate. | `/cert.der` |
| `tls_key_file` | Alternative path to the TLS private key. | `/key.der` |
| `passwd_file` | Path to the file containing user credentials used for authentication. | `/pyrobusta.passwd` |
| `roles_file` | Path to the file containing RBAC role definitions used for authorization. | `/pyrobusta.roles` |
| `log_level` | Logging level. Can be one of: `error`, `warning`, `info`, `debug`. | `info` |
| `socket_max_con` | Maximum number of simultaneous socket connections. | 2 |
| `http_served_paths` | Space-separated list of filesystem paths that may be served over HTTP. | `/www` |
| `http_mem_cap` | Fraction of available heap memory reserved for stream buffers. Valid range: (0, 1]. | 0.1 |
| `http_port` | Port number for HTTP. | 80 |
| `https_port` | Port number for HTTPS. | 443 |
| `http_multipart` | Enables or disables multipart request and response processing (`Content-Type: multipart/*`). | False |
| `http_files_api` | Enables or disables the file management API endpoint (`/files`), allowing upload, download, and listing of files. | False |
| `http_auth` | Selects the type of authentication method enforced by the server. Currently, basic authentication (`basic`) is supported. | None |
| `http_browser_security` | Enables or disables browser security features including browser security headers (Content Security Policy, referrer policy) and CSRF protection (if authentication is enabled). Disabling browser security is only recommended when using non-browser clients or during local development and testing. | True |
| `http_insecure_auth` | Allows clients to authenticate over unsecured HTTP (without TLS). This may expose credentials or authentication tokens in transit. | False |
| `http_sessions` | Enables browser session cookies for authenticated clients. When enabled, successful authentication establishes a session that can be reused without resending authentication credentials. | True |
| `http_session_ttl_sec` | Duration of validity of session cookies in seconds. | 900 |

## Configuration Loading

Configuration is represented by the `Config` class in
`pyrobusta.utils.config`. During application initialization,
`pyrobusta.application` creates and loads a `Config` instance from
`pyrobusta.env`, converting values to their expected runtime types.

Configuration values are exposed as attributes on the `Config` instance:


```
config = Config("/pyrobusta.env")

if config.tls:
    ...
```

The application uses the configuration to initialize and specialize the
relevant subsystems during startup. The `Config` instance is then discarded;
runtime components do not access configuration directly.

Configuration is **immutable for the lifetime of an application**. Changes
to `pyrobusta.env` therefore require a new application instance and, under
normal operation, an application restart.

The `pyrobusta.utils.config` module does not maintain a global configuration
object or runtime configuration cache. It provides the `Config` definition
and configuration-loading functionality.

---

PyRobusta v0.8.0 Web Server
