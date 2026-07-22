"""Custom exceptions for the N1914A power meter driver."""

from __future__ import annotations


class N1914AError(Exception):
    """Base exception for all N1914A driver errors."""


class N1914AConnectionError(N1914AError):
    """Raised when the VISA connection to the instrument cannot be
    established, is lost, or a low-level I/O operation fails."""


class N1914ACommandError(N1914AError):
    """Raised when the instrument's SCPI error queue reports one or
    more errors after a command was sent."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        message = "; ".join(errors) if errors else "Unknown instrument error"
        super().__init__(message)


class N1914AConfigError(N1914AError):
    """Raised when an invalid configuration value or parameter is used."""
