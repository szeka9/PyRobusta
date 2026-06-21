# Configuration parameters

Configuration can be overridden in pyrobusta.env, in .env format. Create pyrobusta.env in the project root, and run ```make deploy-config```
to upload it to the root directory of the target device.

| Name              | Description | Default |
| :---------------- | :---------- | :------ |
| wifi_ssid         | Name of the Wi-Fi network. When empty, Wi-Fi is not initalized by the built-in wifi.py module. | None |
| wifi_password     | Password of the Wi-Fi network. When empty, Wi-Fi is not initalized by the built-in wifi.py module. | None |
| http_port         | Port number for HTTP. | 80 |
| https_port        | Port number for HTTPS. | 443 |
| http_multipart    | Enables or disables multipart request and response processing. Enabling multipart support increases memory usage. | False |
| http_mem_cap      | Fraction of available heap memory reserved for stream buffers; (0;1] | 0.1 |
| http_served_paths | Space-separated list of filesystem paths that may be served over HTTP. | "/www /lib/pyrobusta" |
| http_files_api    | Enables or disables the [file management API](./api.md#file-management-api) endpoint (/files), allowing to upload, download, and list files. | False |
| socket_max_con    | Maximum number of simultaneous socket connections. | 2 |
| tls               | Enables or disables TLS. When enabled, cert.der and key.der must be installed at the server root. | False |
| log_level         | Logging level. Can be one of: warning, info, debug. | "info" |
