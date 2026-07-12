#!/usr/bin/env python3
"""
This test performs soak tests while measuring the heap usage
and other performance metrics with different configurations.
The test is designed to run against a device running the boot.py

Tests are performed with the Locust load testing framework, simulating
multiple concurrent users accessing the device's HTTP server with
different request patterns.

The test workflow includes:
1. Applying a configuration to the device using mpremote.

2. Performing a soak test with Locust, simulating concurrent
   users making requests to the device.

3. Measuring the heap usage of the device during the soak test
   using a dedicated endpoint.

4. Collecting performance metrics such as response times and
   request rates from Locust.

5. Visualizing the results with time series plots of heap usage and a
   summary table of performance metrics for each configuration.
"""

import sys
import math

from http_user import DefaultUser, FilesApiUser, MultipartUser
from load_test import run_test
from device import Device

# ---------------------------
# Test configuration settings
# ---------------------------
TEST_DURATION_MINUTES = 60

base_config = {
    "socket_max_con": 4,
    "http_mem_cap": 0.05,
    "http_multipart": True,
    "http_files_api": True,
    "tls": False,
    "http_port": 8080,
    "https_port": 4443,
    "log_level": "info",
    "http_served_paths": "/lib/pyrobusta /www",
}


def get_test_config(sram_bytes: int, _, buffer_large: int):
    socket_counts = (4,)

    def round_up_sig(x, sig=3):
        """
        Round up with significant digits.
        round_up_sig(0.0012345, 2) == 0.0013
        round_up_sig(0.0012345, 3) == 0.00124
        """
        if x == 0:
            return 0
        factor = 10 ** (sig - int(math.floor(math.log10(abs(x)))) - 1)
        return math.ceil(x * factor) / factor

    test_config = {
        "tls": [
            {
                "http_mem_cap": round_up_sig((buffer_large / sram_bytes) * max_con, 3),
                "tls": True,
                "socket_max_con": max_con,
            }
            for max_con in socket_counts
        ],
    }
    print(test_config)
    return test_config


def main():
    device_id = sys.argv[1]  # mpremote id e.g. a1 (/dev/ttyACM1)
    device_ip = sys.argv[2]
    device_name = sys.argv[3]
    output_path = sys.argv[4]

    if not device_id or not device_ip or not device_name or not output_path:
        raise ValueError(
            "Invalid arguments.\nUsage: test.py device_id device_ip device_name output_path"
        )

    dev = Device(device_id, device_ip, device_name, base_config)

    run_test(
        output_path,
        dev,
        get_test_config,
        [DefaultUser, FilesApiUser, MultipartUser],
        TEST_DURATION_MINUTES,
    )


if __name__ == "__main__":
    main()
