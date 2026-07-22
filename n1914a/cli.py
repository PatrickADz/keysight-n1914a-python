"""Command-line interface for the N1914A driver.

Provides one-shot subcommands (read, zero, configure) and an
interactive shell for bench use, avoiding VISA reconnection overhead
between commands.

Can be invoked either as an installed console script:

    n1914a-cli shell

If a config.ini is present in the current directory (see
config.example.ini), the resource address does not need to be passed
on the command line at all.
"""

from __future__ import annotations

import argparse
import cmd
import logging
import sys
from typing import List, Optional

from .config import load_config
from .driver import N1914A
from .exceptions import N1914AError

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class N1914AShell(cmd.Cmd):
    """Interactive shell for bench testing an N1914A ."""

    intro = "N1914A interactive shell. Type 'help' for commands, 'exit' to quit."
    prompt = "n1914a> "

    def __init__(self, instrument: N1914A):
        super().__init__()
        self.instrument = instrument

    def do_read(self, arg: str) -> None:
        """read [channel] - Fetch the last measurement (default channel 1)."""
        channel = int(arg) if arg.strip() else 1
        print(self.instrument.get_power(channel=channel))

    def do_measure(self, arg: str) -> None:
        """measure [channel] - Trigger and fetch a fresh measurement."""
        channel = int(arg) if arg.strip() else 1
        print(self.instrument.measure_power(channel=channel))

    def do_zero(self, arg: str) -> None:
        """zero [channel] - Zero the sensor (remove RF power first!)."""
        channel = int(arg) if arg.strip() else 1
        print(f"Zeroing channel {channel}, this takes a few seconds...")
        self.instrument.zero(channel=channel)
        print("Done.")

    def do_unit(self, arg: str) -> None:
        """unit DBM|W - Set the measurement unit."""
        if not arg.strip():
            print("Usage: unit DBM|W")
            return
        self.instrument.set_unit(arg.strip())

    def do_errors(self, arg: str) -> None:
        """errors - Drain and print the SCPI error queue."""
        try:
            self.instrument.check_errors(context="manual check")
            print("No errors.")
        except N1914AError as exc:
            print(f"Errors found: {exc}")

    def do_idn(self, arg: str) -> None:
        """idn - Print the instrument identification string."""
        print(self.instrument.idn())

    def do_exit(self, arg: str) -> bool:
        """exit - Close the connection and leave the shell."""
        print("Closing connection...")
        return True

    do_quit = do_exit
    do_EOF = do_exit


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Keysight N1914A power meter CLI")
    parser.add_argument("--config", default=None, help="Path to config.ini")
    parser.add_argument(
        "--address",
        default=None,
        help="VISA resource address override (optional if config.ini is present)",
    )
    parser.add_argument("--channel", type=int, default=None, help="Channel override")

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("shell", help="Start an interactive shell")

    read_parser = subparsers.add_parser("read", help="Fetch the last measurement and exit")
    read_parser.add_argument("--unit", default=None, help="DBM or W")

    zero_parser = subparsers.add_parser("zero", help="Zero the sensor and exit")
    zero_parser.add_argument("--timeout", type=float, default=20.0)

    subparsers.add_parser("idn", help="Print *IDN? and exit")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    config = load_config(
        config_path=args.config,
        resource_address=args.address,
        channel=args.channel,
    )

    try:
        instrument = N1914A(config.resource_address, timeout_ms=config.timeout_ms)
    except N1914AError as exc:
        logger.error("Could not connect to N1914A: %s", exc)
        return 1

    try:
        if args.command == "shell":
            N1914AShell(instrument).cmdloop()
        elif args.command == "read":
            if args.unit:
                instrument.set_unit(args.unit)
            print(instrument.get_power(channel=config.channel))
        elif args.command == "zero":
            instrument.zero(channel=config.channel, timeout_s=args.timeout)
            print("Zeroing complete.")
        elif args.command == "idn":
            print(instrument.idn())
    except N1914AError as exc:
        logger.error("Command failed: %s", exc)
        return 1
    finally:
        instrument.disconnect()

    return 0


if __name__ == "__main__":
    sys.exit(main())
