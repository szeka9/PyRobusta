# pylint: disable=C0413,C0411
import gevent
import gevent.monkey

gevent.monkey.patch_all()

import os
import json
from time import monotonic

import requests
from locust.env import Environment

from device import Device
from http_user import DefaultUser, FilesApiUser, MultipartUser
from summary import generate_measurement_table, generate_plot

import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TEST_IDLE_PERIOD = 30


def interpolate_time_series(usage_data: list):
    """
    Interpolate time-series data to normalize to 1-second intervals
    """
    usage = []
    prev_ts = None
    prev_mem = None

    for u in usage_data:
        ts = u[0]
        mem = u[1]

        if prev_ts is None:
            usage.append(mem)
        else:
            dt = ts - prev_ts
            assert dt > 0

            for i in range(1, dt):
                usage.append(round(prev_mem + (mem - prev_mem) * i / dt))

            usage.append(mem)

        prev_ts = ts
        prev_mem = mem
    return usage


def determine_idle_heap(usage_data: list):
    """
    Determine idle heap usage
    """
    idle_threshold = usage_data[0] * 0.01
    idle_last_idx = 0
    for i, _ in enumerate(usage_data):
        idle_last_idx = i
        if i > 0 and usage_data[i] - usage_data[i - 1] > idle_threshold:
            break
    return round(sum(usage_data[:idle_last_idx]) / (idle_last_idx))


def load_test(config: dict, device: Device, user_classes: list, duration_minutes: int):
    """
    Run load test
    """
    host = device.get_host()
    max_con = config.get("socket_max_con", 1)

    if not user_classes:
        user_classes = [DefaultUser]
        if config.get("http_multipart", False):
            user_classes = [MultipartUser]
        if config.get("http_files_api", False):
            user_classes = [FilesApiUser]

    env = Environment(
        user_classes=user_classes,
        host=host,
    )

    gevent.sleep(TEST_IDLE_PERIOD)  # For idle measurement
    runner = env.create_local_runner()
    runner.start(
        user_count=max_con,
        spawn_rate=max_con,
    )

    end_time = monotonic() + duration_minutes * 60 - 2 * TEST_IDLE_PERIOD
    while True:
        remaining = end_time - monotonic()
        if remaining <= 0:
            break
        gevent.sleep(min(10, remaining))
        print(
            f"users={runner.user_count} "
            f"state={runner.state} "
            f"requests={env.stats.total.num_requests} "
            f"failures={env.stats.total.num_failures}"
        )

    runner.quit()

    gevent.sleep(
        TEST_IDLE_PERIOD + 10
    )  # For idle measurement and heap usage data collection

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
        usage_ts = requests.get(
            f"{host}/heap/time-series",
            verify=False,
            timeout=5,
            headers={"Connection": "close"},
        )
        if usage_ts.headers.get("Content-Type", "").startswith("text/csv"):
            usage = interpolate_time_series(
                [
                    (int(u.split(",", 1)[0]), int(u.split(",", 1)[1]))
                    for u in usage_ts.text.splitlines()
                ]
            )
        else:
            raise ValueError(
                f"Unexpected Content-Type: {usage_ts.headers.get('Content-Type')}"
            )

        print(f"Measured: {usage}")
    except Exception as e:  # pylint: disable=W0718
        # Catch all exceptions without halting test execution
        print(f"WARNING - exception: {e}")
        return 0, [], stats

    return determine_idle_heap(usage), usage, stats


def test_config_delta(
    device: Device,
    config_delta: dict,
    duration_minutes: int,
    user_classes: list,
):
    """
    Test a configuration delta
    """
    target_config = dict(device.base_config)
    target_config.update(config_delta)

    if device.base_config == target_config and config_delta:
        print("Base config matches target config, skipping.")
        return None, None

    if not config_delta:
        print(f"Measure with base config: {device.base_config}")
        target_config = device.base_config
    else:
        print(f"Measure with target config: {target_config}")

    device.apply_config(target_config)
    idle, usage, stats = load_test(
        target_config, device, user_classes, duration_minutes
    )
    return idle, usage, stats


# pylint: disable=R0914
def run_test(
    output_path: str,
    device: Device,
    config_getter: callable,
    user_classes: list = None,
    duration_minutes: int = 5,
    testcase_selector: str = ""
):
    # --------------------------------------------
    # Test base configuration
    # --------------------------------------------
    measurements = []

    if not testcase_selector or testcase_selector == "base":
        device.apply_base_config()

        idle, usage, stats = test_config_delta(
            device,
            {},
            duration_minutes=duration_minutes,
            user_classes=user_classes,
        )

        base_measurement = {
            "id": "base",
            "idle": idle,
            "usage": usage,
            "stats": stats,
            "config": device.base_config,
        }
        measurements.append(base_measurement)
        generate_plot(base_measurement, device.device_name, output_path)

    # --------------------------------------------
    # Test configuration delta
    # --------------------------------------------

    sram_bytes, buffer_small, buffer_large = device.get_mem_params()
    test_config = config_getter(sram_bytes, buffer_small, buffer_large)
    for case_id, case in test_config.items():
        delta_cnt = 0
        for _, delta in enumerate(case):
            delta_cnt += 1
            testcase_id = f"{case_id}_{delta_cnt:03d}"

            if testcase_selector and testcase_selector != testcase_id:
                continue

            load_idle, load_usage, load_stats = test_config_delta(
                device,
                delta,
                duration_minutes=duration_minutes,
                user_classes=user_classes,
            )
            if load_usage and load_stats:
                m = {
                    "id": testcase_id,
                    "idle": load_idle,
                    "usage": load_usage,
                    "stats": load_stats,
                    "config": device.base_config | delta,
                }
                measurements.append(m)
                generate_plot(m, device.device_name, output_path)

    # --------------------------------------------
    # Export measurements
    # --------------------------------------------
    target_dir = device.device_name.replace("-", "_").lower()
    if target_dir not in os.listdir(output_path):
        os.mkdir(f"{output_path}/{target_dir}")

    file_path = f"{output_path}/{target_dir}/measurements.json"
    existing_measurements = []

    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                existing_measurements = json.load(f)

                if not isinstance(existing_measurements, list):
                    existing_measurements = []
        except (json.JSONDecodeError, OSError):
            existing_measurements = []

    # Merge by id, preserving existing entries unless overridden
    merged_measurements = {
        measurement["id"]: measurement
        for measurement in existing_measurements
    }

    for measurement in measurements:
        merged_measurements[measurement["id"]] = measurement

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(list(merged_measurements.values()), f, indent=4)

    print(
        generate_measurement_table(
            measurements,
            excluded_keys={
                "http_port",
                "https_port",
                "http_served_paths",
                "log_level",
            },
        )
    )
