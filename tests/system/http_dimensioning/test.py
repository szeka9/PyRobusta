"""
This test performs load tests while dimensioning the HTTP server
with different configurations, measuring the resulting heap usage
and performance. The test is designed to run against a device
running the boot.py

Tests are performed with the Locust load testing framework, simulating
multiple concurrent users accessing the device's HTTP server with
different request patterns.

The test workflow includes:
1. Applying a configuration to the device using mpremote.

2. Performing a load test with Locust, simulating concurrent
   users making requests to the device.

3. Measuring the heap usage of the device before and after
   the load test using a dedicated endpoint.

4. Collecting performance metrics such as response times and
   request rates from Locust.

5. Visualizing the results with time series plots of heap usage and a
   summary table of performance metrics for each configuration.
"""

from flask import json
from gevent import os
import gevent.monkey

gevent.monkey.patch_all()

import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import gevent
import requests
import sys
import socket
import subprocess
import tempfile
import math

from time import sleep, monotonic
from locust.env import Environment
from locust.stats import stats_printer

from utils import generate_measurement_table, generate_plot
from http_user import DefaultUser, FilesApiUser, MultipartUser

# ---------------------------
# Test configuration settings
# ---------------------------
LOAD_TEST_DURATION = 60

base_config = {
    "socket_max_con": 1,
    "http_mem_cap": 0.05,
    "http_multipart": False,
    "http_files_api": False,
    "tls": False,
    "http_port": 8080,
    "https_port": 4443,
    "log_level": "info",
    "http_served_paths": "/lib/pyrobusta /www",
}


def get_mem_params(device):
    """
    Determine SRAM and buffer settings of a device
    """
    sram_bytes = int(
        subprocess.run(
            [
                "mpremote",
                device,
                "exec",
                "import gc\nprint(gc.mem_free() + gc.mem_alloc())",
            ],
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        ).stdout
    )

    (
        send_buf_min_bytes,
        send_buf_max_bytes,
        recv_buf_min_bytes,
        recv_buf_max_bytes,
        con_overhead,
    ) = [
        int(i)
        for i in subprocess.run(
            [
                "mpremote",
                device,
                "exec",
                (
                    "from pyrobusta.server.http_server import HttpServer\n"
                    "print( HttpServer.SEND_BUF_MIN_BYTES,\n"
                    "HttpServer.SEND_BUF_MAX_BYTES,\n"
                    "HttpServer.RECV_BUF_MIN_BYTES,\n"
                    "HttpServer.RECV_BUF_MAX_BYTES,\n"
                    "HttpServer.CON_OVERHEAD_BYTES,\n"
                    ")"
                ),
            ],
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        ).stdout.split()
    ]

    buffer_small = send_buf_min_bytes + recv_buf_min_bytes + con_overhead
    buffer_large = send_buf_max_bytes + recv_buf_max_bytes + con_overhead
    return sram_bytes, buffer_small, buffer_large


def get_test_config(sram_bytes, buffer_small, buffer_large):
    socket_counts = (1, 2, 4)

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
        "low_mem_cap": [
            {
                "http_mem_cap": round_up_sig((buffer_small / sram_bytes) * max_con, 3),
                "socket_max_con": max_con,
            }
            for max_con in socket_counts
        ],
        "high_mem_cap": [
            {
                "http_mem_cap": round_up_sig((buffer_large / sram_bytes) * max_con, 3),
                "socket_max_con": max_con,
            }
            for max_con in socket_counts
        ],
        "multipart": [
            {
                "http_mem_cap": round_up_sig((buffer_small / sram_bytes) * max_con, 3),
                "http_multipart": True,
                "socket_max_con": max_con,
            }
            for max_con in socket_counts
        ],
        "files_api": [
            {
                "http_mem_cap": round_up_sig((buffer_small / sram_bytes) * max_con, 3),
                "http_files_api": True,
                "socket_max_con": max_con,
            }
            for max_con in socket_counts
        ],
        "tls": [
            {
                "http_mem_cap": round_up_sig((buffer_small / sram_bytes) * max_con, 3),
                "tls": True,
                "socket_max_con": max_con,
            }
            for max_con in socket_counts
        ],
    }
    print(test_config)
    return test_config


# ------------
# Test helpers
# ------------


def apply_mpremote_config(config, device):
    subprocess.run(["mpremote", device, "soft-reset"], check=True)

    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as tmp:
        config_lines = subprocess.run(
            ["mpremote", device, "cat", ":/pyrobusta.env"],
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        ).stdout.splitlines()

        current_config = {}

        for line in config_lines:
            line = line.rstrip("\r\n").split("#")[0]
            if not line.strip():
                continue
            parts = line.split("=", 1)
            key = parts[0].strip()
            value = parts[1].strip().strip("'").strip('"')
            current_config[key] = value

        current_config.update(config)

        tmp.write(
            "\n".join([f"{key}={value}" for key, value in current_config.items()])
            + "\n"
        )
        tmp.flush()

        subprocess.run(
            ["mpremote", device, "cp", tmp.name, ":/pyrobusta.env"], check=True
        )
        subprocess.run(["mpremote", device, "reset"], check=True)
        sleep(15)


def validate_device_ip(device_ip):
    try:
        socket.inet_aton(device_ip)
    except socket.error:
        print(f"Invalid device address: {device_ip}")
        sys.exit(1)


# ------------
# Test methods
# ------------


def load_test(config, device_ip):
    proto = "https" if config["tls"] else "http"
    port = 4443 if config["tls"] else 8080
    host = f"{proto}://{device_ip}:{port}"
    max_con = config.get("socket_max_con", 1)

    user_classes = [DefaultUser]
    if config.get("http_multipart", False):
        user_classes = [MultipartUser]
    if config.get("http_files_api", False):
        user_classes = [FilesApiUser]

    env = Environment(
        user_classes=user_classes,
        host=host,
    )

    runner = env.create_local_runner()
    runner.start(
        user_count=max_con,
        spawn_rate=max_con,
    )

    start_time = monotonic()
    while monotonic() - start_time < LOAD_TEST_DURATION:
        gevent.sleep(5)

        print(
            f"users={runner.user_count} "
            f"state={runner.state} "
            f"requests={env.stats.total.num_requests} "
            f"failures={env.stats.total.num_failures}"
        )

    runner.quit()

    total = env.stats.total
    stats = {
        "ok": total.num_requests,
        "errors": total.num_failures,
        "avg_ms": total.avg_response_time,
        "min_ms": total.min_response_time,
        "max_ms": total.max_response_time,
        "rps": total.current_rps,
        "p95_ms": total.get_response_time_percentile(0.95),
        "p99_ms": total.get_response_time_percentile(0.99),
    }

    try:
        sleep(5)
        usage = requests.get(
            f"{host}/heap/time-series",
            verify=False,
            timeout=5,
            headers={"Connection": "close"},
        ).json()

        print(f"Measured: {usage}")
    except Exception as e:
        print(f"WARNING - exception: {e}")
        return 0, [], stats

    idle_threshold = usage[0] * 0.01
    idle_last_idx = 0
    for i in range(len(usage)):
        idle_last_idx = i
        if i > 0 and usage[i] - usage[i - 1] > idle_threshold:
            break
    idle = round(sum(usage[:idle_last_idx]) / (idle_last_idx))

    return idle, usage, stats


def test_config_delta(device_name, device_ip, base_config, config_delta={}):
    target_config = dict(base_config)
    target_config.update(config_delta)

    if base_config == target_config and config_delta:
        print("Base config matches target config, skipping.")
        return None, None

    if not config_delta:
        print(f"Measure with base config: {base_config}")
        target_config = base_config
    else:
        print(f"Measure with target config: {target_config}")
        pass

    apply_mpremote_config(target_config, device_name)
    idle, usage, stats = load_test(target_config, device_ip)
    return idle, usage, stats


if __name__ == "__main__":
    device_id = sys.argv[1]  # mpremote id e.g. a1 (/dev/ttyACM1)
    device_ip = sys.argv[2]
    device_name = sys.argv[3]

    validate_device_ip(device_ip)
    apply_mpremote_config(base_config, device_id)

    idle, usage, stats = test_config_delta(device_id, device_ip, base_config)

    base_measurement = {
        "id": "base",
        "idle": idle,
        "usage": usage,
        "stats": stats,
        "config": base_config,
    }
    generate_plot(base_measurement, device_name)

    measurements = [base_measurement]
    sram_bytes, buffer_small, buffer_large = get_mem_params(device_id)
    test_config = get_test_config(sram_bytes, buffer_small, buffer_large)
    for case in test_config:
        delta_cnt = 0
        for i, delta in enumerate(test_config[case]):
            load_idle, load_usage, load_stats = test_config_delta(
                device_id, device_ip, base_config, delta
            )
            if load_usage and load_stats:
                delta_cnt += 1
                m = {
                    "id": f"{case}_{delta_cnt:03d}",
                    "idle": load_idle,
                    "usage": load_usage,
                    "stats": load_stats,
                    "config": base_config | delta,
                }
                measurements.append(m)
                generate_plot(m, device_name)

    target_dir = device_name.replace("-", "_").lower()
    if target_dir not in os.listdir("./docs/dimensioning/"):
        os.mkdir(f"./docs/dimensioning/{target_dir}")

    with open(f"docs/dimensioning/{target_dir}/measurements.json", "w") as f:
        json.dump(measurements, f, indent=4)

    table = generate_measurement_table(
        measurements,
        excluded_keys={
            "http_port",
            "https_port",
            "http_served_paths",
            "log_level",
            "http_files_api",
        },
    )

    print(table)
