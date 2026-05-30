"""
Measure memory usage of HTTP server.
"""

import requests
import sys
import socket
import subprocess
import tempfile
import threading
import math

from time import sleep

from utils import generate_measurement_table, generate_plot

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


def measure_footprint(config, device_ip):
    proto = "https" if config["tls"] == True else "http"
    port = 4443 if config["tls"] == True else 8080
    try:
        usage = requests.get(
            f"{proto}://{device_ip}:{port}/mem/current",
            verify=False,
            headers={"Connection": "close"},
        ).text
        print(f"Measured: {usage}")
    except:
        return None
    return int(usage)


# ------------
# Test methods
# ------------


def load_test(config, device_ip):
    proto = "https" if config["tls"] else "http"
    port = 4443 if config["tls"] else 8080
    max_con = config.get("socket_max_con", 1)

    base_url = f"{proto}://{device_ip}:{port}"

    stop_flag = False
    results = {
        "ok": 0,
        "errors": 0,
    }

    lock = threading.Lock()

    def worker():
        nonlocal stop_flag
        while not stop_flag:
            try:
                resp = requests.get(
                    f"{base_url}/index.html",
                    verify=False,
                    timeout=5,
                    headers={"Connection": "close"},
                )
                resp.raise_for_status()

                with lock:
                    results["ok"] += 1

            except Exception:
                with lock:
                    results["errors"] += 1

    threads = []
    for _ in range(max_con):
        t = threading.Thread(target=worker, daemon=True)
        t.start()
        threads.append(t)

    # Run load phase
    sleep(LOAD_TEST_DURATION)

    # Stop workers
    stop_flag = True
    for t in threads:
        t.join(timeout=2)

    try:
        usage = requests.get(
            f"{base_url}/mem/time-series",
            verify=False,
            timeout=5,
            headers={"Connection": "close"},
        ).json()

        print(f"Measured: {usage}")
    except Exception as e:
        print(f"WARNING - exception: {e}")
        return {
            "load": [],
            "load_stats": results,
            "concurrency": max_con,
        }

    return {
        "load": usage,
        "load_stats": results,
        "concurrency": max_con,
    }


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
    idle = measure_footprint(target_config, device_ip)
    load = load_test(target_config, device_ip)
    return idle, load


if __name__ == "__main__":
    device_id = sys.argv[1]  # mpremote id e.g. a1 (/dev/ttyACM1)
    device_ip = sys.argv[2]
    device_name = sys.argv[3]

    validate_device_ip(device_ip)
    apply_mpremote_config(base_config, device_id)

    measured_idle, measured_load = test_config_delta(device_id, device_ip, base_config)
    baseline = {
        "id": "base",
        "idle": measured_idle,
        "config": base_config,
    }
    baseline.update(measured_load)

    measurements = []
    sram_bytes, buffer_small, buffer_large = get_mem_params(device_id)
    test_config = get_test_config(sram_bytes, buffer_small, buffer_large)
    for case in test_config:
        delta_cnt = 0
        for i, delta in enumerate(test_config[case]):
            measured_idle, measured_load = test_config_delta(
                device_id, device_ip, base_config, delta
            )
            if measured_idle and measured_load:
                delta_cnt += 1
                m = {
                    "id": f"{case}_{delta_cnt:03d}",
                    "idle": measured_idle,
                    "delta": delta,
                }
                m.update(measured_load)
                measurements.append(m)

    print(baseline)
    print(measurements)

    table = generate_measurement_table(
        baseline,
        measurements,
        excluded_keys={
            "http_port",
            "https_port",
            "http_served_paths",
            "log_level",
            "http_files_api",
        },
    )

    generate_plot(baseline, device_name)
    for m in measurements:
        generate_plot(m, device_name)

    print(table)
