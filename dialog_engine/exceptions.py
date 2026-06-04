"""Exceptions for the dialog engine."""

from __future__ import annotations


class DialogError(Exception):
    """Base exception for all dialog engine errors."""


class StepNotFoundError(DialogError):
    """Raised when a step ID cannot be resolved."""

    def __init__(self, step_id: str) -> None:
        super().__init__(f"Step {step_id!r} not found")
        self.step_id = step_id


class ValidationError(DialogError):
    """Raised when a submitted answer fails validation."""

    def __init__(self, message: str, step_id: str | None = None) -> None:
        super().__init__(message)
        self.step_id = step_id
