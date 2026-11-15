"""Card numbers are dropped before anything is stored, and /summary answers
with a Bot API 10.4 widget (or a text fallback) only for linked users."""
import json
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app import telegram_bot
from app.models.account import Account
from app.models.auth import TelegramIdentity, TelegramTransactionDraft
from app.models.enums import AccountType
from app.models.workspace import Workspace, WorkspaceStatus
from tests.test_auth_api import _bootstrap_user

TELEGRAM_USER = 434343
STRANGER = 515151
CHAT_ID = 777


class ApiRecorder:
    """Stands in for TelegramBot.api: records calls, optionally fails one method."""

    def __init__(self, fail_method: str | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.fail_method = fail_method

    async def __call__(self, client, method: str, payload: dict) -> dict:
        self.calls.append((method, payload))
        if method == self.fail_method:
            raise telegram_bot.TelegramApiError(method, "Bad Request: test failure")
        return {"ok": True, "result": {}}

    @property
    def methods(self) -> list[str]:
        return [method for method, _ in self.calls]

    def payloads(self, method: str) -> list[dict]:
        return [payload for name, payload in self.calls if name == method]


@pytest.fixture
def bot(test_sessionmaker, monkeypatch):
    # The bot opens its own sessions; point them at the disposable test database.
    monkeypatch.setattr(telegram_bot, "AsyncSessionLocal", test_sessionmaker)
    instance = object.__new__(telegram_bot.TelegramBot)
    instance.webapp_url = ""
    instance.api = ApiRecorder()
    return instance


async def _linked_owner(test_sessionmaker) -> tuple[UUID, UUID]:
    user_id, personal_id, _ = await _bootstrap_user(test_sessionmaker)
    async with test_sessionmaker() as session:
        account = Account(workspace_id=personal_id, name="Kaspi", type=AccountType.DEBIT_CARD, currency="KZT")
        session.add(account)
        await session.flush()
        session.add(TelegramIdentity(
            user_id=user_id,
            default_workspace_id=personal_id,
            default_account_id=account.id,
            telegram_user_id=TELEGRAM_USER,
        ))
        await session.commit()
        return user_id, personal_id


def _message(text: str, *, sender: int = TELEGRAM_USER, entities: list | None = None) -> dict:
    message = {
        "message_id": 55,
        "chat": {"id": CHAT_ID, "type": "private"},
        "from": {"id": sender},
        "text": text,
    }
    if entities is not None:
        message["entities"] = entities
    return message


def _widget_query(data: object = "refresh", *, sender: int = TELEGRAM_USER) -> dict:
    return {
        "id": "wq-1",
        "from": {"id": sender},
        "chat": {"id": CHAT_ID, "type": "private"},
        "message_id": 91,
        "data": data,
    }


async def _draft_count(test_sessionmaker) -> int:
    async with test_sessionmaker() as session:
        return (await session.execute(select(func.count()).select_from(TelegramTransactionDraft))).scalar_one()


@pytest.mark.parametrize(
    ("text", "entities"),
    [
        ("-500 4111 1111 1111 1111", None),
        ("-500 кофе 4111111111111111", None),
        ("-500 карта", [{"type": "bank_card_number", "offset": 5, "length": 5}]),
    ],
)
async def test_card_message_is_deleted_and_never_becomes_a_draft(bot, test_sessionmaker, text, entities):
    await _linked_owner(test_sessionmaker)

    await bot.handle_message(None, _message(text, entities=entities))

    assert bot.api.methods == ["deleteMessage", "sendMessage"]
    assert bot.api.calls[0][1] == {"chat_id": CHAT_ID, "message_id": 55}
    warning = bot.api.calls[1][1]["text"]
    assert "номер банковской карты" in warning
    # The warning must not echo the card back.
    assert "4111" not in warning
    assert await _draft_count(test_sessionmaker) == 0


async def test_card_warning_still_goes_out_when_delete_fails(bot, test_sessionmaker):
    bot.api = ApiRecorder(fail_method="deleteMessage")

    await bot.handle_message(None, _message("4111 1111 1111 1111"))

    assert bot.api.methods == ["deleteMessage", "sendMessage"]
    assert await _draft_count(test_sessionmaker) == 0


async def test_ordinary_quick_entry_is_not_blocked_by_the_card_check(bot, test_sessionmaker):
    await _linked_owner(test_sessionmaker)

    await bot.handle_message(None, _message("-2500 кофе"))

    assert "deleteMessage" not in bot.api.methods
    assert bot.api.methods == ["sendMessage"]
    payload = bot.api.calls[0][1]
    assert payload["text"].startswith("Расход: 2500.00 KZT\nкофе")
    assert "inline_keyboard" in payload["reply_markup"]
    assert await _draft_count(test_sessionmaker) == 1


async def test_summary_for_linked_user_sends_widget(bot, test_sessionmaker):
    await _linked_owner(test_sessionmaker)

    await bot.handle_message(None, _message("/summary"))

    assert bot.api.methods == ["sendWidget"]
    payload = bot.api.calls[0][1]
    assert payload["chat_id"] == CHAT_ID
    assert payload["html"] == telegram_bot.SUMMARY_WIDGET_HTML
    assert payload["height"] == telegram_bot.SUMMARY_WIDGET_HEIGHT
    assert payload["allow_queries"] is True
    assert payload["caption"].startswith("Сводка: ")
    # Figures stay private: the widget is never shared or public.
    assert "public_data" not in payload and "is_shared" not in payload
    assert len(payload["chat_data"].encode("utf-8")) <= 1024
    data = json.loads(payload["chat_data"])
    assert data["m"] and data["c"]
    assert data["c"] == "KZT"


async def test_balance_alias_and_bot_suffix_also_send_widget(bot, test_sessionmaker):
    await _linked_owner(test_sessionmaker)

    await bot.handle_message(None, _message("/balance@AurumBot"))

    assert bot.api.methods == ["sendWidget"]


async def test_summary_falls_back_to_text_when_widget_fails(bot, test_sessionmaker):
    await _linked_owner(test_sessionmaker)
    bot.api = ApiRecorder(fail_method="sendWidget")

    await bot.handle_message(None, _message("/summary"))

    assert bot.api.methods == ["sendWidget", "sendMessage"]
    text = bot.api.calls[1][1]["text"]
    assert text.startswith("Сводка: ")
    assert "Баланс: " in text and "KZT" in text


async def test_summary_for_unlinked_user_asks_to_link(bot, test_sessionmaker):
    await bot.handle_message(None, _message("/summary", sender=STRANGER))

    assert bot.api.methods == ["sendMessage"]
    assert "/link" in bot.api.calls[0][1]["text"]


async def test_widget_refresh_from_linked_user_edits_data_then_answers(bot, test_sessionmaker):
    await _linked_owner(test_sessionmaker)

    await bot.handle_widget_query(None, _widget_query())

    assert bot.api.methods == ["editMessageWidgetData", "answerWidgetQuery"]
    edit = bot.api.calls[0][1]
    assert edit["chat_id"] == CHAT_ID and edit["message_id"] == 91
    assert json.loads(edit["chat_data"])["c"] == "KZT"
    answer = bot.api.calls[1][1]
    assert answer["widget_query_id"] == "wq-1"
    assert json.loads(answer["data"]) == {"ok": True}


async def test_widget_refresh_from_unlinked_user_reveals_nothing(bot, test_sessionmaker):
    await _linked_owner(test_sessionmaker)

    await bot.handle_widget_query(None, _widget_query(sender=STRANGER))

    assert bot.api.methods == ["answerWidgetQuery"]
    assert json.loads(bot.api.calls[0][1]["data"]) == {"error": "unlinked"}


@pytest.mark.parametrize("data", ["delete-all", "", None, {"refresh": True}])
async def test_widget_query_with_unknown_data_fails(bot, test_sessionmaker, data):
    await _linked_owner(test_sessionmaker)

    await bot.handle_widget_query(None, _widget_query(data))

    assert bot.api.methods == ["answerWidgetQuery"]
    assert json.loads(bot.api.calls[0][1]["data"]) == {"error": "failed"}


async def test_widget_refresh_still_answers_when_edit_fails(bot, test_sessionmaker):
    await _linked_owner(test_sessionmaker)
    bot.api = ApiRecorder(fail_method="editMessageWidgetData")

    await bot.handle_widget_query(None, _widget_query())

    assert bot.api.methods == ["editMessageWidgetData", "answerWidgetQuery"]
    assert json.loads(bot.api.calls[1][1]["data"]) == {"error": "failed"}


async def test_card_number_in_photo_caption_is_deleted(bot, test_sessionmaker):
    await _linked_owner(test_sessionmaker)
    message = _message("")
    message["caption"] = "чек 4111 1111 1111 1111"

    await bot.handle_message(None, message)

    assert bot.api.methods == ["deleteMessage", "sendMessage"]


async def test_widget_refresh_in_blocked_space_says_blocked(bot, test_sessionmaker):
    _user_id, personal_id = await _linked_owner(test_sessionmaker)
    async with test_sessionmaker() as session:
        workspace = await session.get(Workspace, personal_id)
        workspace.status = WorkspaceStatus.BLOCKED
        await session.commit()

    await bot.handle_widget_query(None, _widget_query())

    assert bot.api.methods == ["answerWidgetQuery"]
    assert json.loads(bot.api.calls[0][1]["data"]) == {"error": "blocked"}
