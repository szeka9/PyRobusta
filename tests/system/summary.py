import os
import statistics
import sys
import json

import matplotlib.pyplot as plt

from matplotlib.gridspec import GridSpec
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

# -----------------------------------
# Helpers for processing measurements
# -----------------------------------


def generate_measurement_table(measurements: list, excluded_keys: list):
    """
    Generate a table in markdown format for measurement data.
    """
    base = measurements[0]
    config_keys = set(base.get("config", {}).keys())

    for m in measurements[1:]:
        config_keys.update(m.get("config", {}).keys())

    if not excluded_keys:
        excluded_keys = []

    config_keys = sorted(k for k in config_keys if k not in excluded_keys)
    headers = ["id"] + config_keys + ["footprint_bytes"]
    rows = []
    base_cfg = dict(base["config"])
    base_row = [base["id"]]

    # Base config
    for key in config_keys:
        base_row.append(base_cfg.get(key, ""))

    base_row.append(base["idle"])
    rows.append(base_row)

    # Measurements
    for m in measurements[1:]:
        row = [m["id"]]
        for key in config_keys:
            row.append(m["config"].get(key, ""))

        row.append(m["idle"])
        rows.append(row)

    header_line = "| " + " | ".join(headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(str(v) for v in row) + " |" for row in rows]
    return "\n".join([header_line, separator] + body)


def get_y_axis_parameters(data: list):
    step = 4 * 1024
    ymin = min(data)
    ymax = max(data)

    # Round to fixed-interval boundaries
    ymin = ((ymin - step) // step) * step
    ymax = ((ymax + step) // step + 1) * step

    # Generate consistent ticks
    yticks = list(range(int(ymin), int(ymax + 1), 1024))
    return ymin, ymax, yticks


def generate_main_plot(gs: GridSpec, fig: Figure, measurement: dict, device_name: str):
    usage = list(measurement["usage"])
    ax = fig.add_subplot(gs[:, 0])
    ax.set_title(f"Heap usage over time - {device_name} - [{measurement["id"]}]")
    ax.grid(True)

    # ----------------------------
    # X Axis
    # ----------------------------
    ticks_interval = 1
    xlabel = "Time [s]"

    for interval in [600, 300, 60, 30, 15, 10, 5]:
        if len(usage) >= interval * 6:
            ticks_interval = interval
            break

    if ticks_interval >= 60:
        xlabel = "Time [min]"

    expected = (len(usage) - 1) // ticks_interval * ticks_interval + 1
    usage = usage[:expected]
    total_time = len(usage)  # Assuming each index represents 1 second

    ax.plot(range(total_time), usage)
    ax.set_xlabel(xlabel)

    xticks = list(range(0, total_time, ticks_interval))
    ax.set_xticks(xticks)
    ax.set_xticklabels(
        xticks if xlabel == "Time [s]" else [f"{x // 60}" for x in xticks]
    )
    ax.set_xlim(0, total_time - 1)

    # ----------------------------
    # Y Axis
    # ----------------------------
    # Rounded limits with a minimum range
    ax.set_ylabel("Heap usage [KiB]")

    ymin, ymax, yticks = get_y_axis_parameters(usage)
    yticks = yticks[:: max(1, 2 * ((len(yticks) // 8) // 2))]
    ax.set_yticks(yticks)
    ax.set_ylim(ymin, ymax)
    ax.margins(y=0.05)

    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x / 1024:.0f}"))

    # Reference lines
    ax.axhline(min(usage), linestyle=":", linewidth=1)
    ax.axhline(max(usage), linestyle=":", linewidth=1)


def generate_stats_annotation(gs: GridSpec, fig: Figure, measurement: dict):
    stats_ax = fig.add_subplot(gs[0, 1])
    stats_ax.axis("off")

    load_stats = measurement.get("stats", {})
    concurrency = measurement["config"].get("socket_max_con", "n/a")

    annotation_text = "\n".join(
        [
            f"HTTP - 200 OK     {load_stats['ok']}",
            f"HTTP errors       {load_stats['errors']}",
            f"Avg latency       {load_stats['avg_ms']:.0f} ms",
            f"Min latency       {load_stats['min_ms']:.0f} ms",
            f"Max latency       {load_stats['max_ms']:.0f} ms",
            f"RPS               {load_stats['rps']:.2f}",
            f"P95               {load_stats['p95_ms']:.0f} ms",
            f"P99               {load_stats['p99_ms']:.0f} ms",
            f"Concurrency       {concurrency}",
        ]
    )

    stats_ax.text(
        0.03,
        0.98,
        "Test summary",
        fontsize=9,
        fontweight="bold",
        ha="left",
        va="bottom",
        transform=stats_ax.transAxes,
    )

    stats_ax.text(
        0.03,
        0.88,
        annotation_text,
        fontsize=8,
        family="monospace",
        ha="left",
        va="top",
        transform=stats_ax.transAxes,
        bbox={
            "boxstyle": "round,pad=0.45",
            "facecolor": "#fafafa",
            "edgecolor": "0.75",
            "linewidth": 0.8,
        },
    )


def generate_heap_dist_plot(gs: GridSpec, fig: Figure, measurement: dict):
    box_ax = fig.add_subplot(gs[1, 1])

    usage = list(measurement["usage"])
    box_ax.boxplot(
        usage,
        orientation="vertical",
        widths=0.35,
        patch_artist=True,
        showfliers=False,
        whis=(0, 100),
    )

    # Hide top and right border
    box_ax.spines["top"].set_visible(False)
    box_ax.spines["right"].set_visible(False)

    # ----------------------------
    # Statistics
    # ----------------------------
    minimum = min(usage)
    q1 = statistics.quantiles(usage, n=4)[0]
    median = statistics.median(usage)
    q3 = statistics.quantiles(usage, n=4)[2]
    maximum = max(usage)

    labels = (
        f"max {maximum/1024:.1f}\n"
        f"Q3  {q3/1024:.1f}\n"
        f"med {median/1024:.1f}\n"
        f"Q1  {q1/1024:.1f}\n"
        f"min {minimum/1024:.1f}"
    )

    box_ax.text(
        1,
        0.4,
        labels,
        transform=box_ax.transAxes,
        ha="right",
        va="top",
        fontsize=8,
        family="monospace",
        bbox={
            "boxstyle": "round,pad=0.3",
            "facecolor": "white",
            "alpha": 0.8,
        },
    )

    # ----------------------------
    # Y Axis
    # ----------------------------
    box_ax.set_ylabel("Heap distribution [KiB]")

    ymin, ymax, yticks = get_y_axis_parameters(usage)
    yticks = yticks[:: max(1, 2 * ((len(yticks) // 5) // 2))]
    box_ax.set_ylim(ymin, ymax)
    box_ax.set_yticks(yticks)
    box_ax.margins(y=0.05)

    box_ax.tick_params(
        axis="y",
        which="both",
        direction="in",
        pad=-20,  # move labels inward
        length=4,
    )
    box_ax.get_yticklabels()[0].set_visible(False)
    box_ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x / 1024:.0f}"))
    box_ax.grid(True, axis="y", alpha=0.3)

    # ----------------------------
    # X Axis
    # ----------------------------
    box_ax.set_xticks([])
    box_ax.tick_params(axis="x", bottom=False)


def generate_plot(measurement: list, device_name: str, output_path: str):
    """
    Visualize time series data of heap usage with additional annotation.
    """

    fig = plt.figure(figsize=(9, 4.5))
    gs = GridSpec(
        2,
        2,
        width_ratios=[2.5, 1],
        height_ratios=[1, 1.5],
        figure=fig,
        wspace=0.1,
        hspace=0.15,
    )

    generate_main_plot(gs, fig, measurement, device_name)
    generate_stats_annotation(gs, fig, measurement)
    generate_heap_dist_plot(gs, fig, measurement)

    target_dir = device_name.replace("-", "_").lower()
    if target_dir not in os.listdir(output_path):
        os.mkdir(f"{output_path}/{target_dir}")

    fig.savefig(f"{output_path}/{target_dir}/{measurement["id"]}.png", dpi=150)
    plt.close(fig)


def main():
    device_name = sys.argv[1]
    output_path = sys.argv[2]

    target_dir = device_name.replace("-", "_").lower()

    with open(f"{output_path}/{target_dir}/measurements.json", encoding="utf-8") as f:
        measurements = json.loads(f.read())

    for m in measurements:
        generate_plot(m, device_name, output_path)

    table = generate_measurement_table(
        measurements,
        excluded_keys={
            "http_port",
            "https_port",
            "http_served_paths",
            "log_level",
        },
    )
    print(table)


if __name__ == "__main__":
    main()
