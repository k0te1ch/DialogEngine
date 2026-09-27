"""DialogSession — runtime state for one dialog run."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class SessionStatus(StrEnum):
    """Lifecycle state of a dialog session."""

    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass
class DialogSession:
    """Tracks the progress of a single dialog run.

    Attributes:
        dialog_id: ID of the :class:`~dialog_engine.DialogEngine` that owns this session.
        answers:   Collected answers keyed by step ID.
        status:    Current lifecycle state.
        context:   Caller data for this run (language, IDs, values computed by
                   step validators).  Must be JSON-serialisable: it is stored
                   together with the session.
        dialog_version: Schema version of the engine that created the session.
        drafts:    Answers taken back by ``back()`` / ``jump_to()``, keyed by
                   step ID.  Not answers any more — a hint to offer the user
                   the previous value (see :meth:`DialogEngine.keep`).

    Internal:
        _history:  Stack of visited step indices.  ``_history[-1]`` is always
                   the *current* (not yet answered) step.
    """

    dialog_id: str
    answers: dict[str, Any] = field(default_factory=dict)
    status: SessionStatus = SessionStatus.IN_PROGRESS
    context: dict[str, Any] = field(default_factory=dict)
    dialog_version: str | int | None = None
    drafts: dict[str, Any] = field(default_factory=dict)
    _history: list[int] = field(default_factory=list, repr=False)

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def current_index(self) -> int:
        """Zero-based index of the step the user is currently on."""
        return self._history[-1] if self._history else 0

    @property
    def is_active(self) -> bool:
        """``True`` while the session is in progress."""
        return self.status == SessionStatus.IN_PROGRESS

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Serialise session state (e.g. for storage in Redis / DB)."""
        return {
            "dialog_id": self.dialog_id,
            "answers": self.answers,
            "history": list(self._history),
            "status": self.status.value,
            "context": self.context,
            "dialog_version": self.dialog_version,
            "drafts": self.drafts,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DialogSession:
        """Restore a previously serialised session."""
        session = cls(
            dialog_id=data["dialog_id"],
            answers=dict(data.get("answers", {})),
            status=SessionStatus(data.get("status", SessionStatus.IN_PROGRESS)),
            # Sessions saved before 0.3 have no context.
            context=dict(data.get("context") or {}),
            dialog_version=data.get("dialog_version"),
            drafts=dict(data.get("drafts") or {}),
        )
        session._history = list(data.get("history", []))
        return session
