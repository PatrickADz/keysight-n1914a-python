"""Driver for the Keysight/Agilent N1914A power meter.

Communicates over TCP/IP (VXI-11 / LAN) via PyVISA.
"""

from __future__ import annotations

import logging
import time
from types import TracebackType
from typing import List, Optional, Type

import pyvisa

from .exceptions import (
    N1914ACommandError,
    N1914AConfigError,
    N1914AConnectionError,
)

logger = logging.getLogger(__name__)

VALID_UNITS = ("DBM", "W")
VALID_TRIGGER_SOURCES = ("IMM", "EXT", "BUS")
VALID_MEASUREMENT_RATES = ("NORM", "FAST", "DOUB")


class N1914A:
    """Driver for a Keysight N1914A RF power meter.

    Can be used as a context manager::

        with N1914A("TCPIP::192.168.0.4::INSTR") as pm:
            pm.zero()
            print(pm.get_power())
    """

    def __init__(self, resource_address: str, timeout_ms: int = 5000):
        """Initializes the driver and opens the VISA connection.

        Args:
            resource_address: VISA resource string, e.g.
                ``"TCPIP::192.168.0.4::INSTR"``.
            timeout_ms: VISA I/O timeout in milliseconds.

        Raises:
            N1914AConfigError: If ``resource_address`` is empty.
            N1914AConnectionError: If the connection cannot be established.
        """
        if not resource_address:
            raise N1914AConfigError("resource_address must not be empty")

        self.resource_address = resource_address
        self.timeout_ms = timeout_ms
        self.rm: Optional[pyvisa.ResourceManager] = None
        self.instrument: Optional[pyvisa.resources.MessageBasedResource] = None
        self.connect()

    # Connection handling
    def connect(self) -> None:
        """Opens the VISA session and applies default measurement settings.

        Raises:
            N1914AConnectionError: If the resource cannot be opened or the
                instrument does not respond to ``*IDN?``.
        """
        try:
            self.rm = pyvisa.ResourceManager()
            self.instrument = self.rm.open_resource(self.resource_address)
            self.instrument.timeout = self.timeout_ms
            logger.info("Connecting to N1914A at %s", self.resource_address)
        except Exception as exc:
            raise N1914AConnectionError(
                f"Failed to open VISA resource '{self.resource_address}': {exc}"
            ) from exc

        idn = self.idn()
        logger.info("Connected: %s", idn)
        self.check_errors(context="connect")
        self.default_settings()

    def disconnect(self) -> None:
        """Closes the VISA session. Safe to call multiple times."""
        if self.instrument is not None:
            try:
                self.instrument.close()
                logger.info("Disconnected from N1914A")
            except Exception as exc:
                raise N1914AConnectionError(f"Failed to close connection: {exc}") from exc
            finally:
                self.instrument = None

    def __enter__(self) -> "N1914A":
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        self.disconnect()

    # Low-level I/O (never fails silently)
    def _write(self, command: str) -> None:
        """Sends a SCPI command."""
        try:
            self.instrument.write(command)
        except Exception as exc:
            raise N1914AConnectionError(f"Failed to write '{command}': {exc}") from exc

    def _query(self, command: str) -> str:
        """Sends a SCPI query and returns the raw response, stripped."""
        try:
            return self.instrument.query(command).strip()
        except Exception as exc:
            raise N1914AConnectionError(f"Failed to query '{command}': {exc}") from exc

    def check_errors(self, context: str = "") -> List[str]:
        """Drains the SCPI error queue (``SYST:ERR?``) completely.

        Args:
            context: Optional label included in the raised exception to
                identify which operation triggered the check.

        Returns:
            An empty list if no errors were queued.

        Raises:
            N1914ACommandError: If one or more errors were found in the
                instrument's error queue.
        """
        errors: List[str] = []
        while True:
            response = self._query("SYST:ERR?")
            code_str = response.split(",", 1)[0].strip()
            if code_str == "0" or code_str == "+0":
                break
            errors.append(response)
            if len(errors) > 20:
                logger.warning("Error queue still non-empty after 20 reads; aborting drain")
                break
        if errors:
            label = f" during {context}" if context else ""
            logger.error("N1914A reported errors%s: %s", label, errors)
            raise N1914ACommandError(errors)
        return errors

    def idn(self) -> str:
        """Returns the instrument identification string (``*IDN?``)."""
        return self._query("*IDN?")

    # Setup / defaults
    def default_settings(self, channel: int = 1) -> None:
        """Applies a known-good baseline configuration to ``channel``."""
        self.reset()
        self.configure(channel=channel)
        self.set_continuous_mode(channel=channel)
        self.set_trigger_source(channel=channel)
        self.set_averaging_auto(channel=channel)
        self.check_errors(context="default_settings")

    def reset(self) -> None:
        """Resets the power meter to its factory-default state (``*RST``)."""
        self._write("*RST")
        time.sleep(0.5)

    def configure(self, channel: int = 1, function: str = "POW:AC") -> None:
        """Configures a channel's measurement function.

        Reference: N1914A Programming Guide, CONFigure commands (p. 107).
        """
        self._write(f"CONF{channel}:{function}")

    # Trigger / acquisition
    def set_trigger_source(self, channel: int = 1, source: str = "IMM") -> None:
        """Sets the trigger source: ``IMM`` (immediate), ``EXT``, or ``BUS``.

        Reference: TRIGger subsystem, p. 546.
        """
        if source not in VALID_TRIGGER_SOURCES:
            raise N1914AConfigError(f"Invalid trigger source: {source}")
        self._write(f"TRIG{channel}:SOUR {source}")

    def set_continuous_mode(self, channel: int = 1, state: bool = True) -> None:
        """Enables/disables continuous trigger cycling (``INIT:CONT``)."""
        self._write(f"INIT{channel}:CONT {'ON' if state else 'OFF'}")

    def select_channel(self, channel: int = 1) -> None:
        """Selects the active channel on multi-channel mainframes."""
        self._write(f"INST:NSEL {channel}")

    # Measurement
    def get_power(self, channel: int = 1) -> float:
        """Fetches the last completed measurement as a float.

        Uses ``FETCh?``, which retrieves the most recent reading without
        triggering a new acquisition. Use in a continuous-trigger loop
        for streaming/plotting.

        Returns:
            The measured power as a float, in the currently configured
            unit (dBm or W).
        """
        response = self._query(f"FETC{channel}?")
        try:
            return float(response)
        except ValueError as exc:
            raise N1914ACommandError([f"Non-numeric response: '{response}'"]) from exc

    def measure_power(self, channel: int = 1, function: str = "POW:AC") -> float:
        """Configures, triggers, and fetches a fresh reading in one step.

        Equivalent to ``MEAS<ch>:<function>?``. Slower than
        :meth:`get_power` in a continuous loop, but self-contained.
        """
        response = self._query(f"MEAS{channel}:{function}?")
        try:
            return float(response)
        except ValueError as exc:
            raise N1914ACommandError([f"Non-numeric response: '{response}'"]) from exc

    # Units / range
    def set_unit(self, unit: str) -> None:
        """Sets the measurement unit: ``DBM`` or ``W``."""
        unit = unit.upper()
        if unit not in VALID_UNITS:
            raise N1914AConfigError(f"Invalid unit '{unit}'. Use 'DBM' or 'W'.")
        self._write(f"UNIT:POW {unit}")

    def set_range(self, value: int, channel: int = 1) -> None:
        """Manually selects a fixed measurement range."""
        self._write(f"SENS{channel}:RANG {value}")

    def set_range_auto(self, state: bool = True, channel: int = 1) -> None:
        """Enables/disables automatic range selection."""
        self._write(f"SENS{channel}:RANG:AUTO {'ON' if state else 'OFF'}")

    def set_frequency(self, freq_hz: float, channel: int = 1) -> None:
        """Sets the input signal frequency, used to apply the sensor's
        frequency-dependent calibration factor table."""
        self._write(f"SENS{channel}:FREQ {freq_hz}")

    # Averaging / filtering
    def set_averaging(self, count: int, channel: int = 1) -> None:
        """Sets a fixed averaging filter length (disables auto-filtering)."""
        self._write(f"SENS{channel}:AVER:STAT ON")
        self._write(f"SENS{channel}:AVER:COUN {count}")

    def set_averaging_auto(self, state: bool = True, channel: int = 1) -> None:
        """Enables/disables automatic filter length selection.

        Reference: SENSe:AVERage:COUNt:AUTO, p. 11756 of the guide.
        """
        self._write(f"SENS{channel}:AVER:COUN:AUTO {'ON' if state else 'OFF'}")

    def set_measurement_rate(self, rate: str, channel: int = 1) -> None:
        """Sets the measurement speed/resolution trade-off.

        Args:
            rate: One of ``"NORM"`` (normal), ``"FAST"``, or ``"DOUB"``
                (double resolution). ``FAST`` is faster but lower
                resolution; useful for real-time plotting.

        Reference: SENSe:MRATe, p. 403 of the guide.
        """
        rate = rate.upper()
        if rate not in VALID_MEASUREMENT_RATES:
            raise N1914AConfigError(f"Invalid measurement rate: {rate}")
        self._write(f"SENS{channel}:MRAT {rate}")

    # Zeroing / calibration
    def zero(self, channel: int = 1, timeout_s: float = 20.0) -> None:
        """Performs sensor zeroing (``CAL:ZERO:AUTO ONCE``).

        Blocks the RF input internally and takes a few seconds; no RF
        power should be applied to the sensor during this call.

        Args:
            channel: Channel/sensor to zero.
            timeout_s: Maximum time to wait for the operation to complete
                via ``*OPC?`` synchronization.

        Raises:
            N1914ACommandError: If zeroing fails or times out.
        """
        original_timeout = self.instrument.timeout
        try:
            self.instrument.timeout = int(timeout_s * 1000)
            self._write(f"CAL{channel}:ZERO:AUTO ONCE")
            self._query("*OPC?")
        except Exception as exc:
            raise N1914ACommandError([f"Zeroing failed or timed out: {exc}"]) from exc
        finally:
            self.instrument.timeout = original_timeout
        self.check_errors(context="zero")

    def set_reference_calibration_factor(self, percent: float, channel: int = 1) -> None:
        """Sets the sensor's reference calibration factor (``CAL:RCF``),
        typically found on the sensor's calibration certificate/label."""
        self._write(f"CAL{channel}:RCF {percent}")

    def get_reference_calibration_factor(self, channel: int = 1) -> float:
        """Returns the currently set reference calibration factor, in %."""
        return float(self._query(f"CAL{channel}:RCF?"))

    def set_channel_offset(self, offset_db: float, channel: int = 1) -> None:
        """Sets and enables a fixed dB offset (``SENS:CORR:GAIN2``),
        useful to compensate for a known cable or attenuator loss."""
        self._write(f"SENS{channel}:CORR:GAIN2 {offset_db}")
        self._write(f"SENS{channel}:CORR:GAIN2:STAT ON")

    def clear_channel_offset(self, channel: int = 1) -> None:
        """Disables the channel offset applied via :meth:`set_channel_offset`."""
        self._write(f"SENS{channel}:CORR:GAIN2:STAT OFF")
