"""DialogEngine — orchestrates a dialog flow."""

from __future__ import annotations

import inspect
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from .exceptions import DialogError, StepNotFoundError, ValidationError
from .session import DialogSession, SessionStatus
from .step import DialogStep, StepContext, StepValidator
from .validators import async_validate as _async_validate
from .validators import sync_validate as _validate

# ── Text resolver type ────────────────────────────────────────────────────────

TextResolver = Callable[..., str]
AsyncTextResolver = Callable[..., Awaitable[str]]
"""A callable that resolves a step's ``text`` field for display.

Signature (sync or async)::

    def resolver(key: str, answers: dict[str, Any], context: dict[str, Any]) -> str

*key* is ``step.text``; *answers* are the session answers and *context* is
:attr:`DialogSession.context`, so the resolver can pick a language or
interpolate values the caller put there.  The older two-argument form
``resolver(key, answers)`` is still accepted.

The default resolver returns *key* unchanged, which works well when
``text`` already contains the full display string.
"""


def _passthrough_resolver(key: str, _answers: dict[str, Any]) -> str:
    return key


def _takes_context(fn: Callable[..., Any]) -> bool:
    """Whether *fn* accepts a third positional argument (the session context)."""
    try:
        params = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        return False
    positional = 0
    for p in params:
        if p.kind is inspect.Parameter.VAR_POSITIONAL:
            return True
        if p.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            positional += 1
    return positional >= 3


def _finish_translation(
    key: str, raw: str, default: str | None, params: dict[str, Any] | None
) -> str:
    if raw == key:
        return default if default is not None else key
    if not params:
        return raw
    try:
        return raw.format_map(params)
    except (KeyError, IndexError, ValueError):
        # A translation with a broken placeholder is still better than none.
        return raw


class _SummaryAnswers(dict):
    """Answers for ``str.format_map`` that keep unknown placeholders intact."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"

    def __getitem__(self, key: str) -> Any:
        value = super().__getitem__(key) if key in self else self.__missing__(key)
        if isinstance(value, list):
            return ", ".join(str(v) for v in value)
        return "—" if value is None else value


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
        version: str | int | None = None,
    ) -> None:
        """Create an engine for *steps*.

        *version* marks incompatible schema changes: a session saved under
        another version is not restored (see :meth:`restore_session`).
        """
        if not steps:
            raise DialogError("A dialog must have at least one step.")
        self.dialog_id = dialog_id
        self.version = version
        self.steps = list(steps)
        self._by_id: dict[str, int] = {s.id: i for i, s in enumerate(steps)}
        self.text_resolver: TextResolver | AsyncTextResolver = (
            text_resolver or _passthrough_resolver
        )
        self._is_async_resolver = inspect.iscoroutinefunction(self.text_resolver)
        self._resolver_takes_context = _takes_context(self.text_resolver)

    # ── Constructors ──────────────────────────────────────────────────────────

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        text_resolver: TextResolver | AsyncTextResolver | None = None,
        validators: dict[str, StepValidator] | None = None,
    ) -> DialogEngine:
        """Load a dialog from a JSON file.

        Supports both bare-list and wrapped-dict formats (see class docstring).
        *validators* is the same as in :meth:`from_list`.
        """
        path = Path(path)
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            dialog_id: str = raw.get("id", path.stem)
            steps_data: list[dict] = raw["steps"]
            version = raw.get("version")
        else:
            dialog_id = path.stem
            steps_data = raw
            version = None
        engine = cls(
            [DialogStep.from_dict(s) for s in steps_data],
            dialog_id=dialog_id,
            text_resolver=text_resolver,
            version=version,
        )
        engine._attach_validators(validators)
        return engine

    @classmethod
    def from_list(
        cls,
        data: list[dict],
        dialog_id: str = "dialog",
        text_resolver: TextResolver | AsyncTextResolver | None = None,
        validators: dict[str, StepValidator] | None = None,
        version: str | int | None = None,
    ) -> DialogEngine:
        """Create a dialog from a list of step dicts.

        *validators* maps step IDs to :attr:`DialogStep.validator` — the
        schema stays plain data, the code is attached here.
        """
        engine = cls(
            [DialogStep.from_dict(s) for s in data],
            dialog_id=dialog_id,
            text_resolver=text_resolver,
            version=version,
        )
        engine._attach_validators(validators)
        return engine

    # ── Session management ────────────────────────────────────────────────────

    def create_session(
        self, start_index: int = 0, *, context: dict[str, Any] | None = None
    ) -> DialogSession:
        """Create a fresh session starting at *start_index*.

        *context* becomes :attr:`DialogSession.context` (copied); it must be
        JSON-serialisable.
        """
        if not (0 <= start_index < len(self.steps)):
            raise DialogError(
                f"start_index {start_index} is out of range (0–{len(self.steps) - 1})."
            )
        session = DialogSession(
            dialog_id=self.dialog_id,
            context=dict(context or {}),
            dialog_version=self.version,
        )
        session._history = [start_index]
        return session

    def restore_session(self, data: dict[str, Any]) -> DialogSession | None:
        """Restore a session from a previously serialised dict.

        Returns ``None`` when the session is not this dialog's: another
        ``dialog_id``, another :attr:`version` (if the engine has one), or a
        position outside the current schema.  Picking up someone else's
        session would feed answers to the wrong steps.
        """
        session = DialogSession.from_dict(data)
        if session.dialog_id != self.dialog_id:
            return None
        if self.version is not None and session.dialog_version != self.version:
            return None
        if any(not 0 <= i < len(self.steps) for i in session._history):
            return None
        return session

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

        cleaned = _validate(step, value, self._step_context(step, session))
        return self._store_and_advance(session, step, cleaned)

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

        cleaned = await _async_validate(step, value, self._step_context(step, session))
        return self._store_and_advance(session, step, cleaned)

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

        return self._store_and_advance(session, step, None)

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

        return self._store_and_advance(session, step, None)

    def back(self, session: DialogSession) -> DialogStep:
        """Go back to the previous step.

        Its answer moves from ``session.answers`` to ``session.drafts``: the
        step has to be answered again, but :meth:`keep` can resubmit the
        previous value.

        Raises:
            :class:`~dialog_engine.DialogError` if already on the first step.
        """
        self._assert_active(session)
        if len(session._history) <= 1:
            raise DialogError("Already on the first step.")

        # Drop the current (unanswered) step.
        session._history.pop()
        session.return_to = None
        # The step we're returning to will be re-answered: its answer becomes
        # a draft the user can keep.
        prev_step = self.steps[session._history[-1]]
        self._to_draft(session, prev_step.id)
        return prev_step

    async def async_back(self, session: DialogSession) -> DialogStep:
        """Async version of :meth:`back`.

        Raises:
            :class:`~dialog_engine.DialogError` if already on the first step.
        """
        self._assert_active(session)
        if len(session._history) <= 1:
            raise DialogError("Already on the first step.")

        # Drop the current (unanswered) step.
        session._history.pop()
        session.return_to = None
        # The step we're returning to will be re-answered: its answer becomes
        # a draft the user can keep.
        prev_step = self.steps[session._history[-1]]
        self._to_draft(session, prev_step.id)
        return prev_step

    def jump_to(
        self, session: DialogSession, step_id: str, *, return_to: str | None = None
    ) -> DialogStep:
        """Jump directly to the step with the given *step_id*.

        Useful for edit flows where the user wants to revisit a specific step.
        The step's answer moves to ``session.drafts``, as with :meth:`back`.

        With *return_to* (typically a ``confirm`` step), after the edited step
        is answered the dialog follows its route through steps that already
        have answers and stops at *return_to* — or earlier, at the first step
        without an answer (say, a new branch opened by the edit).
        """
        self._assert_active(session)
        idx = self._by_id.get(step_id)
        if idx is None:
            raise StepNotFoundError(step_id)
        if return_to is not None:
            self._lookup(return_to)
        session.return_to = return_to
        session._history.append(idx)
        self._to_draft(session, step_id)
        return self.steps[idx]

    def draft(self, session: DialogSession) -> Any:
        """Previous answer of the current step, if it was taken back; else ``None``."""
        step = self.current_step(session)
        return session.drafts.get(step.id) if step is not None else None

    def keep(self, session: DialogSession) -> DialogStep | None:
        """Resubmit the draft of the current step (the answer given before).

        It goes through validation and branching again, so the route after
        the step follows the kept value.

        Raises:
            :class:`~dialog_engine.DialogError` if the step has no draft.
        """
        return self.submit(session, self._require_draft(session))

    async def async_keep(self, session: DialogSession) -> DialogStep | None:
        """Async version of :meth:`keep`."""
        return await self.async_submit(session, self._require_draft(session))

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

        Passes session answers (and the session context, if the resolver
        takes it) so the resolver can interpolate dynamic values
        (e.g. ``"Hello {name}!"``).
        """
        if self._is_async_resolver:
            raise DialogError(
                "Async text resolver requires calling async_resolve_text() instead"
            )
        text = self.text_resolver(*self._resolver_args(step.text, session))
        return self._fill_summary(step, text, session)

    async def async_resolve_text(
        self,
        step: DialogStep,
        session: DialogSession | None = None,
    ) -> str:
        """Return the display text for *step* via the async :attr:`text_resolver`.

        Arguments are the same as for :meth:`resolve_text`.
        """
        if not self._is_async_resolver:
            return self.resolve_text(step, session)
        text = await self.text_resolver(*self._resolver_args(step.text, session))
        return self._fill_summary(step, text, session)

    def translate(
        self,
        key: str,
        session: DialogSession | None = None,
        *,
        default: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> str:
        """Translate a message *key* (error, button label) via the resolver.

        If the resolver returns *key* unchanged (or raises ``LookupError``),
        the key is unknown to it and *default* is returned as is — or *key*
        itself when there is no default.  A translated text gets *params*
        filled into its ``{placeholders}``.
        """
        if self._is_async_resolver:
            raise DialogError(
                "Async text resolver requires calling async_translate() instead"
            )
        try:
            raw = self.text_resolver(*self._resolver_args(key, session))
        except LookupError:
            raw = key
        return _finish_translation(key, raw, default, params)

    async def async_translate(
        self,
        key: str,
        session: DialogSession | None = None,
        *,
        default: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> str:
        """Async version of :meth:`translate`."""
        if not self._is_async_resolver:
            return self.translate(key, session, default=default, params=params)
        try:
            raw = await self.text_resolver(*self._resolver_args(key, session))
        except LookupError:
            raw = key
        return _finish_translation(key, raw, default, params)

    def resolve_error(
        self, exc: ValidationError, session: DialogSession | None = None
    ) -> str:
        """Display text of a validation error, translated when possible."""
        return self.translate(exc.key, session, default=str(exc), params=exc.params)

    async def async_resolve_error(
        self, exc: ValidationError, session: DialogSession | None = None
    ) -> str:
        """Async version of :meth:`resolve_error`."""
        return await self.async_translate(
            exc.key, session, default=str(exc), params=exc.params
        )

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
        data: dict[str, Any] = {"id": self.dialog_id}
        if self.version is not None:
            data["version"] = self.version
        data["steps"] = [s.to_dict() for s in self.steps]
        return data

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _assert_active(self, session: DialogSession) -> None:
        if not session.is_active:
            raise DialogError(f"Session is {session.status.value}, not in-progress.")

    @staticmethod
    def _fill_summary(
        step: DialogStep, text: str, session: DialogSession | None
    ) -> str:
        """Fill ``{step_id}`` placeholders of a ``confirm`` step with answers.

        Unknown placeholders are left as they are, so a stray brace in the
        text never breaks the summary.
        """
        if step.type != "confirm" or session is None:
            return text
        answers = _SummaryAnswers(session.answers)
        try:
            return text.format_map(answers)
        except (IndexError, ValueError, AttributeError):
            return text

    def _store_and_advance(
        self, session: DialogSession, step: DialogStep, value: Any
    ) -> DialogStep | None:
        session.answers[step.id] = value
        session.drafts.pop(step.id, None)
        next_idx = self._resolve_next_index(step, value, session.current_index)
        if session.return_to is not None:
            next_idx = self._fast_forward(session, next_idx)
        if next_idx is None:
            session.status = SessionStatus.COMPLETED
            session.drafts.clear()
            session.return_to = None
            return None
        session._history.append(next_idx)
        return self.steps[next_idx]

    def _fast_forward(self, session: DialogSession, idx: int | None) -> int | None:
        """Follow the route through answered steps towards ``session.return_to``."""
        seen: set[int] = set()
        while idx is not None and idx not in seen:
            step = self.steps[idx]
            if step.id == session.return_to:
                session.return_to = None
                return idx
            if step.id not in session.answers:
                return idx
            seen.add(idx)
            idx = self._resolve_next_index(step, session.answers[step.id], idx)
        # The route ended (or looped) before reaching the target.
        session.return_to = None
        return idx

    def _to_draft(self, session: DialogSession, step_id: str) -> None:
        if step_id in session.answers:
            session.drafts[step_id] = session.answers.pop(step_id)

    def _require_draft(self, session: DialogSession) -> Any:
        self._assert_active(session)
        step = self._require_current(session)
        if step.id not in session.drafts:
            raise DialogError(f"Step {step.id!r} has no previous answer to keep.")
        return session.drafts[step.id]

    def _attach_validators(self, validators: dict[str, StepValidator] | None) -> None:
        for step_id, fn in (validators or {}).items():
            self.get_step_by_id(step_id).validator = fn

    def _step_context(self, step: DialogStep, session: DialogSession) -> StepContext:
        return StepContext(step=step, answers=session.answers, context=session.context)

    def _resolver_args(
        self, key: str, session: DialogSession | None
    ) -> tuple[Any, ...]:
        answers = session.answers if session is not None else {}
        if not self._resolver_takes_context:
            return key, answers
        context = session.context if session is not None else {}
        return key, answers, context

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
