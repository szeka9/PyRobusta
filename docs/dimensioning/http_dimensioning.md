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
http_serve_files=True
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

| id | http_mem_cap | http_multipart | socket_max_con | tls | footprint_bytes |
| --- | --- | --- | --- | --- | --- |
| base | 0.05 | False | 1 | False | 38512 |
| low_mem_cap_001 | 0.0127 | False | 1 | False | 38512 |
| low_mem_cap_002 | 0.0253 | False | 2 | False | 39728 |
| low_mem_cap_003 | 0.0505 | False | 4 | False | 42112 |
| high_mem_cap_001 | 0.0568 | False | 1 | False | 45680 |
| high_mem_cap_002 | 0.114 | False | 2 | False | 54064 |
| high_mem_cap_003 | 0.228 | False | 4 | False | 70832 |
| multipart_001 | 0.0127 | True | 1 | False | 40608 |
| multipart_002 | 0.0253 | True | 2 | False | 41824 |
| multipart_003 | 0.0505 | True | 4 | False | 44256 |
| tls_001 | 0.0127 | False | 1 | True | 41184 |
| tls_002 | 0.0253 | False | 2 | True | 42400 |
| tls_003 | 0.0505 | False | 4 | True | 44832 |

## Heap usage under network traffic
![image info](./img/esp32_c3/base.png)


# ESP32-S3 (8MB PSRAM)
The table below reports heap consumption after module imports, measured under idle conditions\
with no active network traffic.

## Idle heap usage
| id | http_mem_cap | http_multipart | socket_max_con | tls | footprint_bytes |
| --- | --- | --- | --- | --- | --- |
| base | 0.05 | False | 1 | False | 45520 |
| low_mem_cap_001 | 0.000247 | False | 1 | False | 38352 |
| low_mem_cap_002 | 0.000493 | False | 2 | False | 39568 |
| low_mem_cap_003 | 0.000985 | False | 4 | False | 42000 |
| high_mem_cap_001 | 0.00111 | False | 1 | False | 45520 |
| high_mem_cap_002 | 0.00222 | False | 2 | False | 53904 |
| high_mem_cap_003 | 0.00443 | False | 4 | False | 70672 |
| multipart_001 | 0.000247 | True | 1 | False | 40528 |
| multipart_002 | 0.000493 | True | 2 | False | 41744 |
| multipart_003 | 0.000985 | True | 4 | False | 44176 |
| tls_001 | 0.000247 | False | 1 | True | 40736 |
| tls_002 | 0.000493 | False | 2 | True | 41952 |
| tls_003 | 0.000985 | False | 4 | True | 44384 |

## Heap usage under network traffic
![image info](./img/esp32_s3/base.png)