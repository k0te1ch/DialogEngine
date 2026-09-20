"""Хранение состояния диалога в ``FSMContext`` aiogram.

``DialogSession`` уже умеет ``to_dict()``/``from_dict()``, поэтому адаптеру
остаётся положить её рядом с состоянием интерфейса под одним ключом в данных
FSM. Это даёт главное: при перезапуске процесса (или при ``RedisStorage``)
анкета продолжается с того же шага и в том же сообщении.

Состояние интерфейса — номер страницы, отмеченные варианты, привязка к
сообщению — живёт отдельно от ``session.answers``. Страница пагинации это не
ответ пользователя, и ей нечего делать в результатах анкеты.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aiogram.fsm.context import FSMContext

from dialog_engine.session import DialogSession

from .views import MessageAnchor

DEFAULT_STORAGE_KEY = "dialog_engine"


@dataclass
class DialogUIState:
    """Состояние отображения текущего шага."""

    page: int = 0
    selected: list[str] = field(default_factory=list)
    """Отмеченные, но ещё не подтверждённые варианты шага ``multi_choice``."""

    anchor: MessageAnchor | None = None

    def reset_step(self) -> None:
        """Сбросить всё, что относилось к предыдущему шагу.

        Привязка к сообщению переживает переход: следующий шаг должен
        перерисовать то же самое сообщение.
        """
        self.page = 0
        self.selected = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "page": self.page,
            "selected": list(self.selected),
            "anchor": self.anchor.to_dict() if self.anchor else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DialogUIState:
        raw_anchor = data.get("anchor")
        return cls(
            page=int(data.get("page", 0)),
            selected=list(data.get("selected", [])),
            anchor=MessageAnchor.from_dict(raw_anchor) if raw_anchor else None,
        )


class FSMDialogStorage:
    """Чтение и запись состояния диалога в данных ``FSMContext``."""

    def __init__(self, key: str = DEFAULT_STORAGE_KEY) -> None:
        self.key = key

    async def load(
        self, state: FSMContext
    ) -> tuple[DialogSession | None, DialogUIState]:
        """Вернуть сохранённую сессию и состояние интерфейса.

        Сессия — ``None``, если диалог в этом чате не запускали или он уже
        завершён; состояние интерфейса в этом случае пустое.
        """
        data = await state.get_data()
        raw = data.get(self.key)
        if not raw:
            return None, DialogUIState()
        session = DialogSession.from_dict(raw["session"])
        ui = DialogUIState.from_dict(raw.get("ui", {}))
        return session, ui

    async def save(
        self, state: FSMContext, session: DialogSession, ui: DialogUIState
    ) -> None:
        """Сохранить сессию и состояние интерфейса."""
        await state.update_data(
            {self.key: {"session": session.to_dict(), "ui": ui.to_dict()}}
        )

    async def clear(self, state: FSMContext) -> None:
        """Убрать состояние диалога, не трогая остальные данные FSM.

        ``state.clear()`` здесь не годится: в тех же данных бот держит своё, и
        завершение анкеты не повод это стирать.
        """
        data = await state.get_data()
        if self.key in data:
            data.pop(self.key)
            await state.set_data(data)
