"""DialogStep — a single unit in a dialog flow."""

from __future__ import annotations

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
]

# ── Branching type ────────────────────────────────────────────────────────────
#
#   next: None               → advance sequentially
#   next: "step_id"          → always jump to that step
#   next: {"KEY": "step_id", "_default": "step_id"}
#                            → branch on the submitted answer key;
#                              use "_end" as a value to terminate the dialog.

NextSpec = str | dict[str, str] | None


@dataclass
class DialogStep:
    """A single step in a dialog flow.

    Attributes:
        id:       Unique identifier used for answer storage and branching.
        type:     Input type; determines which validator runs.
        text:     Display text or i18n key passed to the text resolver.
        required: Whether the step must be answered (cannot be skipped).
        choices:  Mapping of key → display text for *choice* / *multi_choice* steps.
        min:      Lower bound.  Meaning depends on type:
                  text → min character length
                  number → min numeric value
                  photo / file → min item count
                  multi_choice → min selected options
        max:      Upper bound (same semantics as *min*).
        pattern:  Regex pattern for *text* steps (applied via ``re.fullmatch``).
        next:     Branching spec (see module docstring).
        meta:     Arbitrary extra data; ignored by the engine.
    """

    id: str
    type: StepType
    text: str
    required: bool = True
    choices: dict[str, str] = field(default_factory=dict)
    min: int | float | None = None
    max: int | float | None = None
    pattern: str | None = None
    next: NextSpec = None
    meta: dict[str, Any] = field(default_factory=dict)

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
        if self.next is not None:
            d["next"] = self.next
        if self.meta:
            d["meta"] = self.meta
        return d
