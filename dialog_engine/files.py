"""File metadata passed as the answer to ``file`` / ``photo`` steps."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class FileInfo:
    """What the engine knows about an uploaded file.

    Only :attr:`file_id` is required; the rest is filled in when the source
    provides it.  Steps with :attr:`~DialogStep.mime_types`,
    :attr:`~DialogStep.extensions` or :attr:`~DialogStep.max_size` treat a
    missing field as a mismatch.
    """

    file_id: str
    mime_type: str | None = None
    file_name: str | None = None
    file_size: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_value(cls, value: Any) -> FileInfo:
        """Build from a :class:`FileInfo`, a dict with its fields or a bare file_id."""
        if isinstance(value, FileInfo):
            return value
        if isinstance(value, dict):
            return cls(
                file_id=str(value["file_id"]),
                mime_type=value.get("mime_type"),
                file_name=value.get("file_name"),
                file_size=value.get("file_size"),
            )
        return cls(file_id=str(value))

    @property
    def extension(self) -> str | None:
        """Lower-case extension with the dot (``".mp3"``), if the name has one."""
        if not self.file_name or "." not in self.file_name:
            return None
        return "." + self.file_name.rsplit(".", 1)[1].lower()


def mime_matches(mime_type: str | None, patterns: list[str]) -> bool:
    """Whether *mime_type* matches one of *patterns* (``"audio/*"`` allowed)."""
    if not mime_type:
        return False
    mime = mime_type.lower()
    for pattern in patterns:
        pattern = pattern.lower()
        if pattern.endswith("/*"):
            if mime.startswith(pattern[:-1]):
                return True
        elif mime == pattern:
            return True
    return False
