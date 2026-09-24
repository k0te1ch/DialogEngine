"""Интеграция dialog_engine с aiogram 3.

Слой собран из независимых частей, чтобы каждую можно было заменить:

* :mod:`.callbacks` — компактный формат ``callback_data`` (лимит 64 байта);
* :mod:`.keyboards` — сборка inline-клавиатуры с пагинацией;
* :mod:`.storage` — сохранение сессии в ``FSMContext``;
* :mod:`.views` — протокол доставки :class:`DialogSender` и реализация
  по умолчанию на обычных сообщениях;
* :mod:`.ephemeral` — доставка эфемерными сообщениями в группах;
* :mod:`.runner` — ход анкеты поверх всего перечисленного;
* :mod:`.router` — фильтры и готовый роутер aiogram.

Пример::

    from aiogram import Dispatcher
    from dialog_engine import DialogEngine
    from dialog_engine.integrations.aiogram import (
        DefaultSender, DialogRunner, build_dialog_router,
    )

    engine = DialogEngine.from_file("dialogs/homework.json")
    runner = DialogRunner(engine)

    dispatcher = Dispatcher()
    dispatcher.include_router(
        build_dialog_router(
            runner,
            sender_factory=DefaultSender,
            on_complete=save_homework,
        )
    )

Пакет импортирует aiogram, поэтому сам ``dialog_engine`` его не трогает:
``import dialog_engine`` работает и без установленного extra ``aiogram``.
"""

from .callbacks import (
    CallbackParseError,
    DialogAction,
    DialogCallback,
    build,
    find_step_by_token,
    step_token,
)
from .ephemeral import EphemeralSender, ephemeral_in_groups
from .keyboards import (
    DEFAULT_LAYOUT,
    KeyboardLayout,
    Option,
    clamp_page,
    options_for_page,
    page_count,
    render_keyboard,
    step_options,
)
from .router import (
    DialogActiveFilter,
    DialogCallbackFilter,
    EventSenderFactory,
    SenderFactory,
    TextAnswerPolicy,
    build_dialog_router,
)
from .runner import DialogRunner, DialogTurn
from .storage import DialogUIState, FSMDialogStorage
from .views import DefaultSender, DialogSender, MessageAnchor, StepView

__all__ = [
    # callbacks
    "CallbackParseError",
    "DialogAction",
    "DialogCallback",
    "build",
    "find_step_by_token",
    "step_token",
    # keyboards
    "DEFAULT_LAYOUT",
    "KeyboardLayout",
    "Option",
    "clamp_page",
    "options_for_page",
    "page_count",
    "render_keyboard",
    "step_options",
    # storage
    "DialogUIState",
    "FSMDialogStorage",
    # views
    "DefaultSender",
    "DialogSender",
    "MessageAnchor",
    "StepView",
    # ephemeral
    "EphemeralSender",
    "ephemeral_in_groups",
    # runner
    "DialogRunner",
    "DialogTurn",
    # router
    "DialogActiveFilter",
    "DialogCallbackFilter",
    "EventSenderFactory",
    "SenderFactory",
    "TextAnswerPolicy",
    "build_dialog_router",
]
