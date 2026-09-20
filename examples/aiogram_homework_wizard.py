"""Мастер добавления домашнего задания на aiogram 3.

Показывает три вещи, ради которых сделан слой интеграции:

* анкета описана данными, а не хендлерами;
* отправка идёт через протокол :class:`DialogSender`, поэтому бот может
  отвечать чем угодно — обычным сообщением, ``sendRichMessage`` с
  ``RichBlockTable`` или эфемерным сообщением в группе;
* состояние живёт в ``FSMContext`` и переживает перезапуск процесса.

Запуск::

    BOT_TOKEN=123:ABC python examples/aiogram_homework_wizard.py
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, TelegramObject

from dialog_engine import DialogEngine
from dialog_engine.integrations.aiogram import (
    DefaultSender,
    DialogRunner,
    KeyboardLayout,
    StepView,
    build_dialog_router,
)

SUBJECTS = {
    "math": "Математика",
    "algo": "Алгоритмы",
    "prog": "Программирование",
    "eng": "Английский",
    "phys": "Физика",
    "hist": "История",
    "phil": "Философия",
    "econ": "Экономика",
    "law": "Право",
}

HOMEWORK_STEPS = [
    {
        "id": "subject",
        "type": "choice",
        "text": "Выберите предмет",
        "choices": SUBJECTS,
    },
    {
        "id": "task",
        "type": "text",
        "text": "Что задали?",
        "min": 3,
        "max": 500,
    },
    {
        "id": "deadline",
        "type": "choice",
        "text": "К какому сроку?",
        "choices": {
            "today": "Сегодня",
            "tomorrow": "Завтра",
            "week": "Через неделю",
        },
    },
]

# Девять предметов не помещаются в один экран — включаем пагинацию по шесть.
LAYOUT = KeyboardLayout(row_width=2, page_size=6, show_cancel=True)

engine = DialogEngine.from_list(HOMEWORK_STEPS, dialog_id="homework")
runner = DialogRunner(engine, layout=LAYOUT)
start_router = Router(name="homework:start")


@start_router.message(CommandStart())
async def start_wizard(message: Message, state: FSMContext) -> None:
    await runner.start(state, DefaultSender(message.bot, message.chat.id))


async def save_homework(event: TelegramObject, answers: dict[str, Any]) -> None:
    """Анкета пройдена — здесь бот сохраняет результат и отвечает по-своему."""
    chat = event.message.chat if isinstance(event, CallbackQuery) else event.chat
    await event.bot.send_message(
        chat.id,
        "Добавлено: {subject} — {task} ({deadline})".format(
            subject=SUBJECTS[answers["subject"]],
            task=answers["task"],
            deadline=answers["deadline"],
        ),
    )


class ProgressSender(DefaultSender):
    """Пример замены доставки: добавляет к вопросу номер шага.

    Подменяется ровно то же место, через которое бот переходит на
    ``sendRichMessage`` или эфемерные сообщения: нужно только реализовать
    ``show`` и вернуть :class:`MessageAnchor` нарисованного сообщения.
    """

    def render_text(self, view: StepView) -> str:
        position, total = view.progress
        question = super().render_text(view)
        return f"Шаг {position} из {total}\n\n{question}"


def build_dispatcher(token: str) -> tuple[Bot, Dispatcher]:
    dispatcher = Dispatcher()
    dispatcher.include_router(start_router)
    dispatcher.include_router(
        build_dialog_router(
            runner,
            sender_factory=ProgressSender,
            on_complete=save_homework,
        )
    )
    return Bot(token), dispatcher


async def main() -> None:
    bot, dispatcher = build_dispatcher(os.environ["BOT_TOKEN"])
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
