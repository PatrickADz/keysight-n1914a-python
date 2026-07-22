"""Live plot of N1914A power readings using matplotlib.

Streams readings with FETCh (via get_power), which does not trigger a new
acquisition each time - the power meter runs continuous-trigger mode
internally, so this loop just polls the last completed measurement. For
faster updates, set a FAST measurement rate before starting the loop.

Usage:
    python examples/continuous_plot.py
    python examples/continuous_plot.py --address TCPIP::192.168.0.4::INSTR
"""

from __future__ import annotations

import argparse
from collections import deque

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

from n1914a import N1914A, load_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Live-plot N1914A power readings")
    parser.add_argument("--config", default=None)
    parser.add_argument("--address", default=None)
    parser.add_argument("--channel", type=int, default=None)
    parser.add_argument(
        "--window", type=int, default=200, help="Number of samples kept on screen"
    )
    parser.add_argument(
        "--interval-ms", type=int, default=200, help="Plot refresh interval in ms"
    )
    args = parser.parse_args()

    config = load_config(
        config_path=args.config, resource_address=args.address, channel=args.channel
    )

    pm = N1914A(config.resource_address, timeout_ms=config.timeout_ms)
    pm.set_unit(config.unit)
    pm.set_measurement_rate("FAST", channel=config.channel)

    samples = deque(maxlen=args.window)

    fig, ax = plt.subplots()
    (line,) = ax.plot([], [], lw=1.5)
    ax.set_xlabel("Sample")
    ax.set_ylabel(f"Power ({config.unit})")
    ax.set_title(f"N1914A live power - channel {config.channel}")
    ax.grid(True, alpha=0.3)

    def update(_frame):
        try:
            value = pm.get_power(channel=config.channel)
        except Exception as exc:  # noqa: BLE001 - keep the plot alive on transient errors
            print(f"Read failed, skipping sample: {exc}")
            return (line,)

        samples.append(value)
        xs = range(len(samples))
        line.set_data(list(xs), list(samples))
        ax.relim()
        ax.autoscale_view()
        return (line,)

    animation = FuncAnimation(fig, update, interval=args.interval_ms, cache_frame_data=False)

    try:
        plt.show()
    finally:
        pm.disconnect()


if __name__ == "__main__":
    main()
