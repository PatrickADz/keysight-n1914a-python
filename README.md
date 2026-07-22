# n1914a-python

Python driver and CLI for the Keysight N1914A RF power meter.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)

## Features

- Full driver for the Keysight N1914A power meter over TCP/IP (VISA / VXI-11).
- Sensor zeroing, reference calibration factor, and channel offset support.
- Configurable measurement rate (`NORM`/`FAST`/`DOUB`) and auto-filtering.
- Layered configuration: CLI arguments → `config.ini` → built-in defaults.
- Interactive shell for bench use - avoids VISA reconnection overhead
  between commands.
- Context manager support (`with N1914A(...) as pm:`).

## Installation

```bash
git clone https://github.com/PatrickADz/keysight-n1914a-python.git
cd keysight-n1914a-python
pip install -e .

# Optional: for the live-plotting example
pip install -e ".[plot]"
```

`pyvisa-py` (the pure-Python VISA backend) is installed automatically as a
dependency, so no separate NI-VISA install is required.

## Quick Start

```python
from n1914a import N1914A

with N1914A("TCPIP::192.168.0.4::INSTR") as pm:
    pm.set_unit("DBM")
    pm.zero()  # remove RF power from the sensor first
    print(pm.get_power())
```

Copy `config.example.ini` to `config.ini` in your working directory and fill
in the real instrument address (real `config.ini` files are git-ignored).
Once that's in place, the address does **not** need to be passed on the
command line:

```bash
# equivalent invocations - use whichever style you prefer
n1914a-cli shell
python -m n1914a shell

# other subcommands
n1914a-cli read
n1914a-cli zero
n1914a-cli idn

# --address overrides config.ini if you need to point at a different unit
n1914a-cli --address TCPIP::10.0.0.7::INSTR read
```

## Repository Structure

```
n1914a/
  __init__.py      - public package API
  __main__.py       - enables `python -m n1914a`
  driver.py         - N1914A driver class
  config.py         - layered configuration loader
  cli.py            - CLI + interactive shell
  exceptions.py     - custom exception hierarchy
tests/
  test_driver.py     - mock-based test suite
examples/
  basic_read.py       - connect, zero, single reading
  continuous_plot.py  - live matplotlib plot of power readings
config.example.ini
pyproject.toml
LICENSE
```

## Tests

```bash
pip install -e ".[dev]"
pytest
```

All tests run against a `FakeInstrument`/`FakeResourceManager` pair - no
physical power meter is required.

## Context / Notes

Developed for RF power measurement tasks at CePIA (Universidad de
Concepción).

## License

MIT - see [LICENSE](LICENSE).

