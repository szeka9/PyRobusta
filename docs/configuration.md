# Configuration parameters

Configuration can be overridden in pyrobusta.env, in .env format. Create pyrobusta.env in the project root, and run ```make deploy-config```
to upload it to the root directory of the target device.

| Name              | Description                                                                                           | Default                       |
|-------------------|-------------------------------------------------------------------------------------------------------|-------------------------------|
| wifi_ssid         | Name of the Wi-Fi network. When empty, Wi-Fi is not initalized by the built-in wifi.py module.        | None                          |
| wifi_password     | Password of the Wi-Fi network. When empty, Wi-Fi is not initalized by the built-in wifi.py module.    | None                          |
| http_multipart    | Enable multipart HTTP requests/responses.                                                             | "False"                       |
| http_mem_cap      | Max memory cap (% × 0.01) of usable heap for HTTP request/response stream buffers.                    | 0.1                           |
| http_served_paths | Space delimited list of filesystem paths allowed to be served through HTTP.                           | "pyrobusta lib"               |
| socket_max_con    | Max number of socket connections of any enabled application server.                                   | 2                             |
| tls               | Enable/disable TLS. When turned on, cert.der/key.der must be installed at the root.                   | "False"                       |
| log_level         | Can be one of: warning, info, debug.                                                                  | "warning"                     |
