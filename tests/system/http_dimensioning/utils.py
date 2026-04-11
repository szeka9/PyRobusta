import os
import matplotlib.pyplot as plt

# -----------------------------------
# Helpers for processing measurements
# -----------------------------------


def generate_measurement_table(base, measurements, excluded_keys={}):
    """
    Generate a table in markdown format for measurement data.
    """
    config_keys = set(base.get("config", {}).keys())

    for m in measurements:
        config_keys.update(m.get("delta", {}).keys())

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
    for m in measurements:
        effective_cfg = dict(base_cfg)
        effective_cfg.update(m.get("delta", {}))

        row = [m["id"]]
        for key in config_keys:
            row.append(effective_cfg.get(key, ""))

        row.append(m["idle"])
        rows.append(row)

    header_line = "| " + " | ".join(headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(str(v) for v in row) + " |" for row in rows]
    return "\n".join([header_line, separator] + body)


def generate_plot(measurement, device_name):
    """
    Visualize time series data of heap usage with additional annotation.
    """
    id = measurement["id"]

    try:
        last_idx = measurement["load"].index(0, 1)
    except ValueError:
        last_idx = len(measurement["load"])

    xticks = list(range(last_idx))

    fig, ax = plt.subplots()
    p = ax.plot(xticks, measurement["load"][0:last_idx])
    plt.title(f"Heap usage over time - {device_name}\n{id}")
    plt.grid(True)
    plt.xlabel("Time [s]")
    plt.ylabel("Heap usage [bytes]")
    plt.xticks(xticks)
    for i, label in enumerate(ax.xaxis.get_ticklabels()):
        if i % 5 == 0:
            label.set_visible(True)
        else:
            label.set_visible(False)

    # Additional annotation
    load_stats = measurement.get("load_stats", {})
    concurrency = measurement.get("concurrency", "n/a")

    ok = load_stats.get("ok", 0)
    errors = load_stats.get("errors", 0)

    annotation_text = f"concurrency: {concurrency}\n" f"ok: {ok}\n" f"errors: {errors}"

    plt.gca().text(
        0.02,
        0.98,
        annotation_text,
        transform=plt.gca().transAxes,
        fontsize=9,
        verticalalignment="top",
        bbox=dict(boxstyle="round", alpha=0.3),
    )

    target_dir = device_name.replace("-", "_").lower()
    if target_dir not in os.listdir("./docs/dimensioning/img/"):
        os.mkdir(f"./docs/dimensioning/img/{target_dir}")

    plt.savefig(f"./docs/dimensioning/img/{target_dir}/{id}.png")
    plt.clf()
