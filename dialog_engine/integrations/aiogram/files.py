"""Извлечение метаданных файла из сообщения aiogram."""

from __future__ import annotations

from aiogram.types import Message

from dialog_engine.files import FileInfo

FILE_ATTRIBUTES = ("document", "audio", "video", "voice", "animation", "video_note")
"""Поля сообщения с одиночным файлом, в порядке проверки."""


def message_files(message: Message) -> list[FileInfo]:
    """Файлы сообщения как :class:`~dialog_engine.FileInfo`.

    У фото берётся самый крупный размер: Telegram присылает несколько превью
    одного снимка. У фото нет имени и MIME-типа — Telegram всегда отдаёт
    JPEG, поэтому ``mime_type`` ставится ``image/jpeg``.
    """
    if message.photo:
        largest = max(message.photo, key=lambda p: p.width * p.height)
        return [
            FileInfo(
                file_id=largest.file_id,
                mime_type="image/jpeg",
                file_size=largest.file_size,
            )
        ]
    for attribute in FILE_ATTRIBUTES:
        media = getattr(message, attribute)
        if media is not None:
            return [
                FileInfo(
                    file_id=media.file_id,
                    mime_type=getattr(media, "mime_type", None),
                    file_name=getattr(media, "file_name", None),
                    file_size=media.file_size,
                )
            ]
    return []
