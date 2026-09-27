"""Exceptions for the dialog engine."""

from __future__ import annotations


class DialogError(Exception):
    """Base exception for all dialog engine errors."""


class StepNotFoundError(DialogError):
    """Raised when a step ID cannot be resolved."""

    def __init__(self, step_id: str) -> None:
        super().__init__(f"Step {step_id!r} not found")
        self.step_id = step_id


class SessionExpiredError(DialogError):
    """Raised when acting on a session whose time-to-live has run out."""


class ValidationError(DialogError):
    """Raised when a submitted answer fails validation.

    Attributes:
        step_id: Step the answer was for.
        key:     Message key for the text resolver.  Built-in errors use keys
                 from :data:`~dialog_engine.messages.DEFAULT_MESSAGES`; for a
                 custom error it defaults to *message*, so raising
                 ``ValidationError("my.key")`` lets the resolver translate it.
        params:  Values for the placeholders of the translated text.
    """

    def __init__(
        self,
        message: str,
        step_id: str | None = None,
        *,
        key: str | None = None,
        params: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.step_id = step_id
        self.key = key if key is not None else message
        self.params = dict(params or {})
