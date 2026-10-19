"""Text resolution helpers: resolver types, translation and ``confirm`` summaries."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from .session import DialogSession
from .step import DialogStep

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


def passthrough_resolver(key: str, _answers: dict[str, Any]) -> str:
    return key


def takes_context(fn: Callable[..., Any]) -> bool:
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


def finish_translation(
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


def fill_summary(step: DialogStep, text: str, session: DialogSession | None) -> str:
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
