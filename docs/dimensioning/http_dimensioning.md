Use the following measurement data to guide configuration choices when dimensioning the\
HTTP server for specific constraints such as memory footprint, request throughput, and\
feature enablement (e.g., TLS, multipart handling, file serving).

The tables below are derived from controlled benchmarks. Each measurement varies a subset\
of parameters relative to a defined baseline configuration.

```.env
# Base configuration
socket_max_con=1
http_mem_cap=0.05
http_multipart=False
http_files_api=False
tls=False
http_port=8080
https_port=4443
log_level=info
http_served_paths=/lib/pyrobusta /www
```

# ESP32-C3 "SuperMini" (ESP32-C3FH4)
The ESP32-C3 provides approximately 162KB of usable heap. It is recommended to limit the maximum\
number of socket connections to 2 (socket_max_con).

## Idle heap usage
The table below reports heap consumption after module imports, measured under idle conditions\
with no active network traffic.

| id | http_files_api | http_mem_cap | http_multipart | socket_max_con | tls | footprint_bytes |
| --- | --- | --- | --- | --- | --- | --- |
| [base](./esp32_c3/base.png) | False | 0.05 | False | 1 | False | 36867 |
| [low_mem_cap_001](./esp32_c3/low_mem_cap_001.png) | False | 0.0127 | False | 1 | False | 36867 |
| [low_mem_cap_002](./esp32_c3/low_mem_cap_002.png) | False | 0.0253 | False | 2 | False | 38083 |
| [low_mem_cap_003](./esp32_c3/low_mem_cap_003.png) | False | 0.0505 | False | 4 | False | 40515 |
| [high_mem_cap_001](./esp32_c3/high_mem_cap_001.png) | False | 0.0568 | False | 1 | False | 45556 |
| [high_mem_cap_002](./esp32_c3/high_mem_cap_002.png) | False | 0.114 | False | 2 | False | 52493 |
| [high_mem_cap_003](./esp32_c3/high_mem_cap_003.png) | False | 0.228 | False | 4 | False | 69189 |
| [multipart_001](./esp32_c3/multipart_001.png) | False | 0.0127 | True | 1 | False | 46268 |
| [multipart_002](./esp32_c3/multipart_002.png) | False | 0.0253 | True | 2 | False | 45347 |
| [multipart_003](./esp32_c3/multipart_003.png) | False | 0.0505 | True | 4 | False | 47781 |
| [files_api_001](./esp32_c3/files_api_001.png) | True | 0.0127 | False | 1 | False | 44232 |
| [files_api_002](./esp32_c3/files_api_002.png) | True | 0.0253 | False | 2 | False | 45411 |
| [files_api_003](./esp32_c3/files_api_003.png) | True | 0.0505 | False | 4 | False | 47846 |
| [tls_001](./esp32_c3/tls_001.png) | False | 0.0127 | False | 1 | True | 41062 |
| [tls_002](./esp32_c3/tls_002.png) | False | 0.0253 | False | 2 | True | 40211 |
| [tls_003](./esp32_c3/tls_003.png) | False | 0.0505 | False | 4 | True | 42643 |

## Heap usage under network traffic
![image info](./esp32_c3/base.png)


# ESP32-S3 (8MB PSRAM)
The table below reports heap consumption after module imports, measured under idle conditions\
with no active network traffic.

## Idle heap usage
| id | http_files_api | http_mem_cap | http_multipart | socket_max_con | tls | footprint_bytes |
| --- | --- | --- | --- | --- | --- | --- |
| [base](./esp32_s3/base.png) | False | 0.05 | False | 1 | False | 45475 |
| [low_mem_cap_001](./esp32_s3/low_mem_cap_001.png) | False | 0.000247 | False | 1 | False | 38385 |
| [low_mem_cap_002](./esp32_s3/low_mem_cap_002.png) | False | 0.000493 | False | 2 | False | 37991 |
| [low_mem_cap_003](./esp32_s3/low_mem_cap_003.png) | False | 0.000985 | False | 4 | False | 40423 |
| [high_mem_cap_001](./esp32_s3/high_mem_cap_001.png) | False | 0.00111 | False | 1 | False | 45516 |
| [high_mem_cap_002](./esp32_s3/high_mem_cap_002.png) | False | 0.00222 | False | 2 | False | 54597 |
| [high_mem_cap_003](./esp32_s3/high_mem_cap_003.png) | False | 0.00443 | False | 4 | False | 69094 |
| [multipart_001](./esp32_s3/multipart_001.png) | False | 0.000247 | True | 1 | False | 46250 |
| [multipart_002](./esp32_s3/multipart_002.png) | False | 0.000493 | True | 2 | False | 45319 |
| [multipart_003](./esp32_s3/multipart_003.png) | False | 0.000985 | True | 4 | False | 47751 |
| [files_api_001](./esp32_s3/files_api_001.png) | True | 0.000247 | False | 1 | False | 44102 |
| [files_api_002](./esp32_s3/files_api_002.png) | True | 0.000493 | False | 2 | False | 45318 |
| [files_api_003](./esp32_s3/files_api_003.png) | True | 0.000985 | False | 4 | False | 47751 |
| [tls_001](./esp32_s3/tls_001.png) | False | 0.000247 | False | 1 | True | 38835 |
| [tls_002](./esp32_s3/tls_002.png) | False | 0.000493 | False | 2 | True | 40055 |
| [tls_003](./esp32_s3/tls_003.png) | False | 0.000985 | False | 4 | True | 42487 |

## Heap usage under network traffic
![image info](./esp32_s3/base.png)