"""DialogStep — a single unit in a dialog flow."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

# ── Public type alias ────────────────────────────────────────────────────────

StepType = Literal[
    "text",
    "number",
    "email",
    "boolean",
    "choice",
    "multi_choice",
    "photo",
    "file",
    "confirm",
]

# ── Branching type ────────────────────────────────────────────────────────────
#
#   next: None               → advance sequentially
#   next: "step_id"          → always jump to that step
#   next: {"KEY": "step_id", "_default": "step_id"}
#                            → branch on the submitted answer key;
#                              use "_end" as a value to terminate the dialog.

NextSpec = str | dict[str, str] | None


@dataclass(frozen=True, slots=True)
class StepContext:
    """What a step validator sees besides the value itself.

    Attributes:
        step:    The step being answered.
        answers: Answers collected so far (read it, don't mutate it).
        context: The session context; a validator may write to it, e.g. to
                 pass a computed value to the text of the following steps.
    """

    step: DialogStep
    answers: dict[str, Any]
    context: dict[str, Any]


StepValidator = Callable[[Any, StepContext], Any | Awaitable[Any]]
"""Per-step validator: ``(value, ctx) -> cleaned`` (sync or async).

Receives the value already checked by the built-in validator of the step type.
Returns the value to store; ``None`` keeps the value it received. Raises
:class:`~dialog_engine.ValidationError` to reject the answer.
"""


@dataclass
class DialogStep:
    """A single step in a dialog flow.

    Attributes:
        id:       Unique identifier used for answer storage and branching.
        type:     Input type; determines which validator runs.
        text:     Display text or i18n key passed to the text resolver.
        required: Whether the step must be answered (cannot be skipped).
        choices:  Mapping of key → display text for *choice* / *multi_choice* steps.
                  For a *confirm* step: step ID → label of its "edit" button.
        min:      Lower bound.  Meaning depends on type:
                  text → min character length
                  number → min numeric value
                  photo / file → min item count
                  multi_choice → min selected options
        max:      Upper bound (same semantics as *min*).
        pattern:  Regex pattern for *text* steps (applied via ``re.fullmatch``).
        mime_types: Allowed MIME types for *file* / *photo* steps
                  (``"audio/*"`` matches the whole family).
        extensions: Allowed file extensions (``".mp3"``; case-insensitive).
        max_size: Largest accepted file, in bytes.
        next:     Branching spec (see module docstring).
        meta:     Arbitrary extra data; ignored by the engine.
        validator: Optional :data:`StepValidator` run after the built-in
                  checks.  Code, not data: it is not serialised by
                  :meth:`to_dict` and has to be attached after
                  :meth:`from_dict`.
    """

    id: str
    type: StepType
    text: str
    required: bool = True
    choices: dict[str, str] = field(default_factory=dict)
    min: int | float | None = None
    max: int | float | None = None
    pattern: str | None = None
    mime_types: list[str] = field(default_factory=list)
    extensions: list[str] = field(default_factory=list)
    max_size: int | None = None
    next: NextSpec = None
    meta: dict[str, Any] = field(default_factory=dict)
    validator: StepValidator | None = field(default=None, repr=False, compare=False)

    @property
    def has_file_constraints(self) -> bool:
        """Whether the step checks file metadata, not only the count."""
        return bool(self.mime_types or self.extensions or self.max_size is not None)

    # ── Construction ──────────────────────────────────────────────────────────

    @classmethod
    def from_dict(cls, data: dict) -> DialogStep:
        """Create a step from a plain dict (e.g. parsed JSON).

        Accepted keys mirror the field names; legacy ``min_photos`` /
        ``max_photos`` are also recognised for backward compatibility.
        """
        return cls(
            id=data["id"],
            type=data["type"],
            text=data["text"],
            required=data.get("required", True),
            choices=data.get("choices", {}),
            min=data.get("min", data.get("min_photos")),
            max=data.get("max", data.get("max_photos")),
            pattern=data.get("pattern"),
            mime_types=list(data.get("mime_types", [])),
            extensions=list(data.get("extensions", [])),
            max_size=data.get("max_size"),
            next=data.get("next"),
            meta=data.get("meta", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialise this step back to a plain dict."""
        d: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "text": self.text,
            "required": self.required,
        }
        if self.choices:
            d["choices"] = self.choices
        if self.min is not None:
            d["min"] = self.min
        if self.max is not None:
            d["max"] = self.max
        if self.pattern is not None:
            d["pattern"] = self.pattern
        if self.mime_types:
            d["mime_types"] = self.mime_types
        if self.extensions:
            d["extensions"] = self.extensions
        if self.max_size is not None:
            d["max_size"] = self.max_size
        if self.next is not None:
            d["next"] = self.next
        if self.meta:
            d["meta"] = self.meta
        return d
