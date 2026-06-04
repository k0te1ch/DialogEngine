"""DialogEngine — orchestrates a dialog flow."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from .exceptions import DialogError, StepNotFoundError
from .session import DialogSession, SessionStatus
from .step import DialogStep
from .validators import async_validate as _async_validate
from .validators import sync_validate as _validate

# ── Text resolver type ────────────────────────────────────────────────────────

TextResolver = Callable[[str, dict[str, Any]], str]
AsyncTextResolver = Callable[[str, dict[str, Any]], Awaitable[str]]
"""A callable that resolves a step's ``text`` field for display.

Signature::

    def resolver(key: str, context: dict[str, Any]) -> str: ...

*key* is ``step.text``; *context* carries the session answers so
the resolver can interpolate dynamic values.

The default resolver returns *key* unchanged, which works well when
``text`` already contains the full display string.
"""


def _passthrough_resolver(key: str, _ctx: dict[str, Any]) -> str:
    return key


# ── Engine ────────────────────────────────────────────────────────────────────


class DialogEngine:
    """Universal multi-step dialog engine.

    The engine owns the *schema* (steps + branching logic) and is
    stateless with respect to individual runs.  All mutable state lives
    in :class:`~dialog_engine.DialogSession` objects.

    Typical usage::

        engine = DialogEngine.from_file("dialogs/onboarding.json")

        session = engine.create_session()
        step = engine.current_step(session)        # → first step
        print(engine.resolve_text(step, session))  # display the question

        next_step = engine.submit(session, "Alice")
        # … repeat until next_step is None (dialog complete)

    JSON format
    -----------
    Bare list::

        [{"id": "name", "type": "text", "text": "Your name?"}, …]

    Wrapped dict (recommended — carries ``id`` and optional metadata)::

        {
          "id": "onboarding",
          "steps": [{"id": "name", "type": "text", "text": "Your name?"}, …]
        }

    Branching example::

        {
          "id": "country",
          "type": "choice",
          "text": "Choose country",
          "choices": {"RU": "Russia", "OTHER": "Other"},
          "next": {"RU": "passport_ru", "OTHER": "passport_other"}
        }

    Use ``"_end"`` as a branch target to terminate the dialog early.
    """

    def __init__(
        self,
        steps: list[DialogStep],
        dialog_id: str = "dialog",
        text_resolver: TextResolver | AsyncTextResolver | None = None,
    ) -> None:
        if not steps:
            raise DialogError("A dialog must have at least one step.")
        self.dialog_id = dialog_id
        self.steps = list(steps)
        self._by_id: dict[str, int] = {s.id: i for i, s in enumerate(steps)}
        self.text_resolver: TextResolver | AsyncTextResolver = (
            text_resolver or _passthrough_resolver
        )
        self._is_async_resolver = asyncio.iscoroutinefunction(text_resolver)

    # ── Constructors ──────────────────────────────────────────────────────────

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        text_resolver: TextResolver | None = None,
    ) -> DialogEngine:
        """Load a dialog from a JSON file.

        Supports both bare-list and wrapped-dict formats (see class docstring).
        """
        path = Path(path)
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            dialog_id: str = raw.get("id", path.stem)
            steps_data: list[dict] = raw["steps"]
        else:
            dialog_id = path.stem
            steps_data = raw
        return cls(
            [DialogStep.from_dict(s) for s in steps_data],
            dialog_id=dialog_id,
            text_resolver=text_resolver,
        )

    @classmethod
    def from_list(
        cls,
        data: list[dict],
        dialog_id: str = "dialog",
        text_resolver: TextResolver | None = None,
    ) -> DialogEngine:
        """Create a dialog from a list of step dicts."""
        return cls(
            [DialogStep.from_dict(s) for s in data],
            dialog_id=dialog_id,
            text_resolver=text_resolver,
        )

    # ── Session management ────────────────────────────────────────────────────

    def create_session(self, start_index: int = 0) -> DialogSession:
        """Create a fresh session starting at *start_index*."""
        if not (0 <= start_index < len(self.steps)):
            raise DialogError(
                f"start_index {start_index} is out of range (0–{len(self.steps) - 1})."
            )
        session = DialogSession(dialog_id=self.dialog_id)
        session._history = [start_index]
        return session

    def restore_session(self, data: dict[str, Any]) -> DialogSession:
        """Restore a session from a previously serialised dict."""
        return DialogSession.from_dict(data)

    # ── Navigation ────────────────────────────────────────────────────────────

    def current_step(self, session: DialogSession) -> DialogStep | None:
        """Return the step the user is currently on, or ``None`` if finished."""
        if not session.is_active:
            return None
        return self.steps[session.current_index]

    def submit(self, session: DialogSession, value: Any) -> DialogStep | None:
        """Submit an answer for the current step.

        Validates *value*, stores it in the session, and advances to the
        next step.

        Returns:
            The next :class:`~dialog_engine.DialogStep`, or ``None`` when
            the dialog is complete.

        Raises:
            :class:`~dialog_engine.ValidationError` if *value* is invalid.
            :class:`~dialog_engine.DialogError` if the session is not active.
        """
        self._assert_active(session)
        step = self._require_current(session)

        cleaned = _validate(step, value)
        session.answers[step.id] = cleaned

        next_idx = self._resolve_next_index(step, cleaned, session.current_index)
        if next_idx is None:
            session.status = SessionStatus.COMPLETED
            return None

        session._history.append(next_idx)
        return self.steps[next_idx]

    async def async_submit(
        self, session: DialogSession, value: Any
    ) -> DialogStep | None:
        """Submit an answer for the current step asynchronously.

        Validates *value*, stores it in the session, and advances to the
        next step.

        Returns:
            The next :class:`~dialog_engine.DialogStep`, or ``None`` when
            the dialog is complete.

        Raises:
            :class:`~dialog_engine.ValidationError` if *value* is invalid.
            :class:`~dialog_engine.DialogError` if the session is not active.
        """
        self._assert_active(session)
        step = self._require_current(session)

        cleaned = await _async_validate(step, value)
        session.answers[step.id] = cleaned

        next_idx = self._resolve_next_index(step, cleaned, session.current_index)
        if next_idx is None:
            session.status = SessionStatus.COMPLETED
            return None

        session._history.append(next_idx)
        return self.steps[next_idx]

    def skip(self, session: DialogSession) -> DialogStep | None:
        """Skip the current *optional* step (``required=False``).

        Returns:
            The next step, or ``None`` if the dialog is complete.

        Raises:
            :class:`~dialog_engine.DialogError` if the step is required.
        """
        self._assert_active(session)
        step = self._require_current(session)
        if step.required:
            raise DialogError(f"Step {step.id!r} is required and cannot be skipped.")

        session.answers[step.id] = None
        next_idx = self._resolve_next_index(step, None, session.current_index)
        if next_idx is None:
            session.status = SessionStatus.COMPLETED
            return None

        session._history.append(next_idx)
        return self.steps[next_idx]

    async def async_skip(self, session: DialogSession) -> DialogStep | None:
        """Skip the current *optional* step (``required=False``) asynchronously.

        Returns:
            The next step, or ``None`` if the dialog is complete.

        Raises:
            :class:`~dialog_engine.DialogError` if the step is required.
        """
        self._assert_active(session)
        step = self._require_current(session)
        if step.required:
            raise DialogError(f"Step {step.id!r} is required and cannot be skipped.")

        session.answers[step.id] = None
        next_idx = self._resolve_next_index(step, None, session.current_index)
        if next_idx is None:
            session.status = SessionStatus.COMPLETED
            return None

        session._history.append(next_idx)
        return self.steps[next_idx]

    def back(self, session: DialogSession) -> DialogStep:
        """Go back to the previous step and clear its stored answer.

        Raises:
            :class:`~dialog_engine.DialogError` if already on the first step.
        """
        self._assert_active(session)
        if len(session._history) <= 1:
            raise DialogError("Already on the first step.")

        # Drop the current (unanswered) step.
        session._history.pop()
        # The step we're returning to will be re-answered, so clear its value.
        prev_step = self.steps[session._history[-1]]
        session.answers.pop(prev_step.id, None)
        return prev_step

    async def async_back(self, session: DialogSession) -> DialogStep:
        """Go back to the previous step and clear its stored answer asynchronously.

        Raises:
            :class:`~dialog_engine.DialogError` if already on the first step.
        """
        self._assert_active(session)
        if len(session._history) <= 1:
            raise DialogError("Already on the first step.")

        # Drop the current (unanswered) step.
        session._history.pop()
        # The step we're returning to will be re-answered, so clear its value.
        prev_step = self.steps[session._history[-1]]
        session.answers.pop(prev_step.id, None)
        return prev_step

    def jump_to(self, session: DialogSession, step_id: str) -> DialogStep:
        """Jump directly to the step with the given *step_id*.

        Useful for edit flows where the user wants to revisit a specific step.
        The step's previous answer is cleared so it can be re-submitted.
        """
        self._assert_active(session)
        idx = self._by_id.get(step_id)
        if idx is None:
            raise StepNotFoundError(step_id)
        session._history.append(idx)
        session.answers.pop(step_id, None)
        return self.steps[idx]

    def cancel(self, session: DialogSession) -> None:
        """Mark the session as cancelled."""
        session.status = SessionStatus.CANCELLED

    # ── Queries ───────────────────────────────────────────────────────────────

    def resolve_text(
        self,
        step: DialogStep,
        session: DialogSession | None = None,
    ) -> str:
        """Return the display text for *step* via the :attr:`text_resolver`.

        Passes session answers as context so the resolver can interpolate
        dynamic values (e.g. ``"Hello {name}!"``).
        """
        ctx: dict[str, Any] = session.answers if session is not None else {}
        if self._is_async_resolver:
            raise DialogError(
                "Async text resolver requires calling async_resolve_text() instead"
            )
        return self.text_resolver(step.text, ctx)

    async def async_resolve_text(
        self,
        step: DialogStep,
        session: DialogSession | None = None,
    ) -> str:
        """Return the display text for *step* via the async :attr:`text_resolver`.

        Passes session answers as context so the resolver can interpolate
        dynamic values (e.g. ``"Hello {name}!"``).
        """
        ctx: dict[str, Any] = session.answers if session is not None else {}
        if not self._is_async_resolver:
            return self.resolve_text(step, session)
        return await self.text_resolver(step.text, ctx)

    def get_step(self, index: int) -> DialogStep | None:
        """Return the step at *index*, or ``None`` if out of range."""
        return self.steps[index] if 0 <= index < len(self.steps) else None

    def get_step_by_id(self, step_id: str) -> DialogStep:
        """Return the step with the given ID.

        Raises :class:`~dialog_engine.StepNotFoundError` if not found.
        """
        idx = self._by_id.get(step_id)
        if idx is None:
            raise StepNotFoundError(step_id)
        return self.steps[idx]

    def progress(self, session: DialogSession) -> tuple[int, int]:
        """Return ``(step_number, total)`` for display (e.g. "Step 2 of 5").

        *step_number* is 1-based.
        """
        return len(session._history), len(self.steps)

    def is_last(self, index: int) -> bool:
        """``True`` if *index* refers to the last step."""
        return index >= len(self.steps) - 1

    def total(self) -> int:
        """Total number of steps in this dialog."""
        return len(self.steps)

    def to_dict(self) -> dict[str, Any]:
        """Serialise the dialog schema to a plain dict."""
        return {
            "id": self.dialog_id,
            "steps": [s.to_dict() for s in self.steps],
        }

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _assert_active(self, session: DialogSession) -> None:
        if not session.is_active:
            raise DialogError(f"Session is {session.status.value}, not in-progress.")

    def _require_current(self, session: DialogSession) -> DialogStep:
        step = self.current_step(session)
        if step is None:
            raise DialogError("No current step.")
        return step

    def _resolve_next_index(
        self,
        step: DialogStep,
        answer: Any,
        current_index: int,
    ) -> int | None:
        """Compute the index of the next step.

        Returns ``None`` to signal end-of-dialog.
        """
        if step.next is None:
            # Sequential advancement.
            nxt = current_index + 1
            return nxt if nxt < len(self.steps) else None

        if isinstance(step.next, str):
            # Unconditional jump.
            if step.next == "_end":
                return None
            return self._lookup(step.next)

        # Conditional branch dict.
        branch_map: dict[str, str] = step.next
        key = str(answer) if answer is not None else "_default"
        target_id = branch_map.get(key) or branch_map.get("_default")

        if target_id is None:
            # No matching branch → fall through sequentially.
            nxt = current_index + 1
            return nxt if nxt < len(self.steps) else None

        if target_id == "_end":
            return None

        return self._lookup(target_id)

    def _lookup(self, step_id: str) -> int:
        idx = self._by_id.get(step_id)
        if idx is None:
            raise StepNotFoundError(step_id)
        return idx
