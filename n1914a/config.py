"""Layered configuration loader for the N1914A driver.

Resolution order (highest priority first):
    1. Explicit CLI arguments
    2. ``config.ini`` file (see ``config.example.ini``)
    3. Built-in defaults
"""

from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

DEFAULT_CONFIG_FILENAME = "config.ini"

DEFAULTS = {
    "resource_address": "TCPIP::192.168.0.4::INSTR",
    "timeout_ms": "5000",
    "channel": "1",
    "unit": "DBM",
}


@dataclass
class N1914AConfig:
    """Resolved configuration for connecting to an N1914A power meter."""

    resource_address: str
    timeout_ms: int
    channel: int
    unit: str


def load_config(
    config_path: Optional[Union[str, Path]] = None,
    *,
    resource_address: Optional[str] = None,
    timeout_ms: Optional[int] = None,
    channel: Optional[int] = None,
    unit: Optional[str] = None,
) -> N1914AConfig:
    """Builds an :class:`N1914AConfig` by layering defaults, an optional
    ``config.ini`` file, and explicit keyword overrides (e.g. from a CLI).

    Args:
        config_path: Path to a config.ini file. If ``None``, looks for
            ``config.ini`` in the current working directory; if that is
            also absent, defaults are used silently.
        resource_address: Overrides the VISA resource string.
        timeout_ms: Overrides the VISA I/O timeout in milliseconds.
        channel: Overrides the default measurement channel.
        unit: Overrides the default power unit (``DBM`` or ``W``).

    Returns:
        A fully resolved :class:`N1914AConfig`.
    """
    values = dict(DEFAULTS)

    path = Path(config_path) if config_path else Path(DEFAULT_CONFIG_FILENAME)
    if path.is_file():
        parser = configparser.ConfigParser()
        parser.read(path)
        if parser.has_section("n1914a"):
            values.update(parser["n1914a"])

    if resource_address is not None:
        values["resource_address"] = resource_address
    if timeout_ms is not None:
        values["timeout_ms"] = str(timeout_ms)
    if channel is not None:
        values["channel"] = str(channel)
    if unit is not None:
        values["unit"] = unit

    return N1914AConfig(
        resource_address=values["resource_address"],
        timeout_ms=int(values["timeout_ms"]),
        channel=int(values["channel"]),
        unit=values["unit"].upper(),
    )
