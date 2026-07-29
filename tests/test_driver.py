"""Mock-based tests for the N1914A driver. No hardware required.

A FakeInstrument stands in for the PyVISA resource and a FakeResourceManager
stands in for pyvisa.ResourceManager, so N1914A() can be exercised end to end.
"""

from __future__ import annotations

from typing import List, Optional

import pytest

from n1914a.driver import N1914A
from n1914a.exceptions import N1914ACommandError, N1914AConfigError, N1914AConnectionError


class FakeInstrument:
    """Minimal fake of a pyvisa MessageBasedResource for N1914A testing."""

    def __init__(self):
        self.timeout = 5000
        self.written: List[str] = []
        self.error_queue: List[str] = ["+0,\"No error\""]
        self._power_value = "-12.34"
        self.closed = False

    def write(self, command: str) -> None:
        self.written.append(command)

    def query(self, command: str) -> str:
        self.written.append(command)
        if command == "*IDN?":
            return "Keysight,N1914A,MY00000001,1.0\n"
        if command == "SYST:ERR?":
            if len(self.error_queue) > 1:
                return self.error_queue.pop(0)
            return self.error_queue[0]
        if command.startswith("FETC") or command.startswith("MEAS"):
            return self._power_value
        if command == "*OPC?":
            return "1"
        if command.startswith("CAL") and command.endswith("RCF?"):
            return "98.5"
        return "0"

    def close(self) -> None:
        self.closed = True


class FakeResourceManager:
    def __init__(self):
        self.opened_with: Optional[str] = None
        self.instrument = FakeInstrument()

    def open_resource(self, resource_address: str):
        self.opened_with = resource_address
        return self.instrument


@pytest.fixture
def patched_pyvisa(monkeypatch):
    fake_rm = FakeResourceManager()
    monkeypatch.setattr(
        "n1914a.driver.pyvisa.ResourceManager", lambda: fake_rm
    )
    return fake_rm


@pytest.fixture
def instrument(patched_pyvisa) -> N1914A:
    return N1914A("TCPIP::192.168.0.4::INSTR")


class TestConnection:
    def test_connect_opens_correct_resource(self, patched_pyvisa):
        N1914A("TCPIP::10.0.0.5::INSTR")
        assert patched_pyvisa.opened_with == "TCPIP::10.0.0.5::INSTR"

    def test_empty_address_raises_config_error(self):
        with pytest.raises(N1914AConfigError):
            N1914A("")

    def test_idn_returns_identification_string(self, instrument):
        assert "N1914A" in instrument.idn()

    def test_context_manager_disconnects(self, patched_pyvisa):
        with N1914A("TCPIP::192.168.0.4::INSTR") as pm:
            assert pm.instrument is not None
        assert patched_pyvisa.instrument.closed is True

    def test_disconnect_is_idempotent(self, instrument):
        instrument.disconnect()
        instrument.disconnect()  # must not raise


class TestErrorHandling:
    def test_check_errors_raises_on_queued_error(self, instrument, patched_pyvisa):
        patched_pyvisa.instrument.error_queue = [
            "-113,\"Undefined header\"",
            "+0,\"No error\"",
        ]
        with pytest.raises(N1914ACommandError):
            instrument.check_errors()

    def test_check_errors_clean_returns_empty_list(self, instrument, patched_pyvisa):
        patched_pyvisa.instrument.error_queue = ["+0,\"No error\""]
        assert instrument.check_errors() == []

    def test_write_failure_raises_connection_error(self, instrument):
        def broken_write(cmd):
            raise IOError("simulated bus failure")

        instrument.instrument.write = broken_write
        with pytest.raises(N1914AConnectionError):
            instrument._write("*RST")


class TestMeasurement:
    def test_get_power_returns_float(self, instrument, patched_pyvisa):
        patched_pyvisa.instrument._power_value = "-5.67"
        assert instrument.get_power() == pytest.approx(-5.67)

    def test_get_power_non_numeric_raises_command_error(self, instrument, patched_pyvisa):
        patched_pyvisa.instrument._power_value = "GARBAGE"
        with pytest.raises(N1914ACommandError):
            instrument.get_power()

    def test_measure_power_sends_correct_query(self, instrument, patched_pyvisa):
        instrument.measure_power(channel=2, function="POW:AC")
        assert "MEAS2:POW:AC?" in patched_pyvisa.instrument.written


class TestConfiguration:
    def test_set_unit_valid(self, instrument, patched_pyvisa):
        instrument.set_unit("dbm")
        assert "UNIT:POW DBM" in patched_pyvisa.instrument.written

    def test_set_unit_invalid_raises(self, instrument):
        with pytest.raises(N1914AConfigError):
            instrument.set_unit("VOLTS")

    def test_set_trigger_source_invalid_raises(self, instrument):
        with pytest.raises(N1914AConfigError):
            instrument.set_trigger_source(source="FOO")

    def test_set_measurement_rate_invalid_raises(self, instrument):
        with pytest.raises(N1914AConfigError):
            instrument.set_measurement_rate("SLOW")

    def test_set_measurement_rate_valid(self, instrument, patched_pyvisa):
        instrument.set_measurement_rate("fast", channel=1)
        assert "SENS1:MRAT FAST" in patched_pyvisa.instrument.written


class TestCalibrationAndOffset:
    def test_zero_sends_expected_sequence(self, instrument, patched_pyvisa):
        instrument.zero(channel=1)
        assert "CAL1:ZERO:AUTO ONCE" in patched_pyvisa.instrument.written

    def test_reference_calibration_factor_roundtrip(self, instrument, patched_pyvisa):
        instrument.set_reference_calibration_factor(98.5, channel=1)
        assert "CAL1:RCF 98.5" in patched_pyvisa.instrument.written
        assert instrument.get_reference_calibration_factor(channel=1) == pytest.approx(98.5)

    def test_set_channel_offset_enables_and_sets_value(self, instrument, patched_pyvisa):
        instrument.set_channel_offset(-10, channel=1)
        assert "SENS1:CORR:GAIN2 -10" in patched_pyvisa.instrument.written
        assert "SENS1:CORR:GAIN2:STAT ON" in patched_pyvisa.instrument.written

    def test_clear_channel_offset(self, instrument, patched_pyvisa):
        instrument.clear_channel_offset(channel=1)
        assert "SENS1:CORR:GAIN2:STAT OFF" in patched_pyvisa.instrument.written
