"""dialog_engine — universal multi-step dialog engine.

Quick start::

    from dialog_engine import DialogEngine

    engine = DialogEngine.from_file("dialogs/onboarding.json")
    session = engine.create_session()

    while (step := engine.current_step(session)) is not None:
        answer = input(engine.resolve_text(step, session) + " ")
        try:
            engine.submit(session, answer)
        except ValidationError as exc:
            print("Error:", exc)

Public API
----------
Classes:
    DialogEngine    — loads a dialog schema, drives navigation
    DialogSession   — mutable run-time state for one dialog instance
    DialogStep      — a single step in the dialog schema
    SessionStatus   — enum: IN_PROGRESS / COMPLETED / CANCELLED

Exceptions:
    DialogError         — base exception
    StepNotFoundError   — unknown step ID referenced
    ValidationError     — submitted answer fails validation

Types:
    StepType        — Literal union of all supported step type strings
    TextResolver    — Callable used by the engine to resolve display text
"""

from .engine import DialogEngine, TextResolver
from .exceptions import DialogError, StepNotFoundError, ValidationError
from .session import DialogSession, SessionStatus
from .step import DialogStep, StepType
from .validators import validate

__version__ = "0.1.1"  # x-release-please-version

__all__ = [
    # Engine
    "DialogEngine",
    "TextResolver",
    # Session
    "DialogSession",
    "SessionStatus",
    # Step
    "DialogStep",
    "StepType",
    # Validators
    "validate",
    # Exceptions
    "DialogError",
    "StepNotFoundError",
    "ValidationError",
    # Metadata
    "__version__",
]
