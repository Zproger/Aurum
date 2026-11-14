"""Small long-polling Telegram bot for linking and launching the Aurum Mini App."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
import json
import logging
import re
from uuid import UUID

import httpx
from fastapi import HTTPException
from sqlalchemy import select

from app.api.deps import RequestWorkspace
from app.api.routes.transactions import _apply_categorization_rule, _currency_fields
from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models.account import Account
from app.models.auth import TelegramIdentity, TelegramTransactionDraft
from app.models.enums import TransactionType
from app.models.transaction import Transaction
from app.models.workspace import User, UserStatus, Workspace, WorkspaceMembership, WorkspaceRole, WorkspaceStatus
from app.schemas.dashboard import DashboardSummary
from app.services.dashboard_service import get_dashboard_summary
from app.services.telegram_sensitive import has_bank_card_number
from app.services.telegram_service import consume_link_code
from app.telegram_widget import (
    SUMMARY_WIDGET_HEIGHT,
    SUMMARY_WIDGET_HTML,
    summary_caption,
    summary_chat_data,
    summary_text,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
ROLE_LABELS = {
    WorkspaceRole.OWNER: "владелец",
    WorkspaceRole.EDITOR: "редактор",
    WorkspaceRole.VIEWER: "только просмотр",
}
TRANSACTION_RE = re.compile(r"^([+-])\s*(\d+(?:[.,]\d{1,2})?)\s+(.{1,255})$", re.DOTALL)


@dataclass(frozen=True)
class SummaryUnavailable:
    """Why /summary cannot be shown: `code` goes to the widget, `text` to the chat."""

    code: str
    text: str


def parse_quick_transaction(text: str) -> tuple[TransactionType, Decimal, str] | None:
    match = TRANSACTION_RE.fullmatch(text.strip())
    if match is None:
        return None
    try:
        amount = Decimal(match.group(2).replace(",", ".")).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None
    description = match.group(3).strip()
    if amount <= 0 or amount >= Decimal("1000000000000") or not description:
        return None
    tx_type = TransactionType.EXPENSE if match.group(1) == "-" else TransactionType.INCOME
    return tx_type, amount, description


class TelegramBot:
    def __init__(self) -> None:
        settings = get_settings()
        self.token = settings.telegram_bot_token.get_secret_value()
        self.webapp_url = (
            settings.telegram_webapp_url.rstrip("/")
            if settings.telegram_mini_app_enabled
            else ""
        )
        self.hmac_secret = settings.auth_hmac_secret.get_secret_value()
        if not self.token:
            raise RuntimeError("AURUM_TELEGRAM_BOT_TOKEN is not configured")
        self.base_url = f"https://api.telegram.org/bot{self.token}"

    async def api(self, client: httpx.AsyncClient, method: str, payload: dict) -> dict:
        response = await client.post(f"{self.base_url}/{method}", json=payload)
        response.raise_for_status()
        body = response.json()
        if not body.get("ok"):
            raise RuntimeError(f"Telegram API method {method} failed")
        return body

    async def send(self, client: httpx.AsyncClient, chat_id: int, text: str, *, open_app: bool = False) -> None:
        payload: dict = {"chat_id": chat_id, "text": text}
        if open_app and self.webapp_url:
            payload["reply_markup"] = {
                "inline_keyboard": [[{
                    "text": "Открыть Aurum",
                    "web_app": {"url": self.webapp_url},
                }]]
            }
        await self.api(client, "sendMessage", payload)

    async def linked_context(self, session, telegram_user_id: int):
        return (
            await session.execute(
                select(TelegramIdentity, User, WorkspaceMembership, Workspace)
                .join(User, User.id == TelegramIdentity.user_id)
                .join(
                    WorkspaceMembership,
                    (WorkspaceMembership.user_id == User.id)
                    & (WorkspaceMembership.workspace_id == TelegramIdentity.default_workspace_id),
                )
                .join(Workspace, Workspace.id == WorkspaceMembership.workspace_id)
                .where(
                    TelegramIdentity.telegram_user_id == telegram_user_id,
                    User.status == UserStatus.ACTIVE,
                    WorkspaceMembership.revoked_at.is_(None),
                )
            )
        ).one_or_none()

    async def memberships(self, session, user_id: UUID) -> list[tuple[WorkspaceMembership, Workspace]]:
        """Every space this Aurum user can currently open, personal first.

        Spaces blocked by an administrator are left out, so neither the picker
        nor a stale button can switch quick entry into them.
        """
        rows = await session.execute(
            select(WorkspaceMembership, Workspace)
            .join(Workspace, Workspace.id == WorkspaceMembership.workspace_id)
            .where(
                WorkspaceMembership.user_id == user_id,
                WorkspaceMembership.revoked_at.is_(None),
                Workspace.status == WorkspaceStatus.ACTIVE,
            )
            .order_by(Workspace.kind.desc(), Workspace.display_name)
        )
        return [(membership, workspace) for membership, workspace in rows.all()]

    async def send_space_picker(self, client: httpx.AsyncClient, chat_id: int, telegram_user_id: int) -> None:
        async with AsyncSessionLocal() as session:
            identity = (
                await session.execute(
                    select(TelegramIdentity).where(TelegramIdentity.telegram_user_id == telegram_user_id)
                )
            ).scalar_one_or_none()
            if identity is None:
                await self.send(client, chat_id, "Сначала привяжите аккаунт командой /link КОД.")
                return
            spaces = await self.memberships(session, identity.user_id)
            current = identity.default_workspace_id
        rows = [[{
            "text": f"{'✓ ' if workspace.id == current else ''}{workspace.display_name} · {ROLE_LABELS[membership.role]}"[:64],
            "callback_data": f"ws:{workspace.id.hex}",
        }] for membership, workspace in spaces]
        await self.api(client, "sendMessage", {
            "chat_id": chat_id,
            "text": "В какое пространство записывать транзакции? Mini App тоже будет открываться в нём.",
            "reply_markup": {"inline_keyboard": rows},
        })

    async def select_space(self, telegram_user_id: int, workspace_hex: str) -> str:
        async with AsyncSessionLocal() as session:
            identity = (
                await session.execute(
                    select(TelegramIdentity).where(TelegramIdentity.telegram_user_id == telegram_user_id)
                )
            ).scalar_one_or_none()
            if identity is None:
                return "Сначала привяжите аккаунт командой /link КОД."
            try:
                workspace_id = UUID(hex=workspace_hex)
            except ValueError:
                return "Пространство недоступно"
            # Membership is re-checked here: a stale button must not grant access.
            chosen = next(
                ((membership, workspace) for membership, workspace in await self.memberships(session, identity.user_id)
                 if workspace.id == workspace_id),
                None,
            )
            if chosen is None:
                return "Пространство недоступно"
            membership, workspace = chosen
            if identity.default_workspace_id != workspace.id:
                identity.default_workspace_id = workspace.id
                identity.default_account_id = None
            accounts = list((
                await session.execute(
                    select(Account)
                    .where(Account.workspace_id == workspace.id, Account.is_archived.is_(False))
                    .order_by(Account.id)
                )
            ).scalars())
            if identity.default_account_id is None and len(accounts) == 1:
                identity.default_account_id = accounts[0].id
            await session.commit()
            account = next((item for item in accounts if item.id == identity.default_account_id), None)
        answer = f"Пространство: {workspace.display_name}"
        if membership.role == WorkspaceRole.VIEWER:
            answer += "\nЗдесь у вас только просмотр — записывать транзакции нельзя."
        elif account is not None:
            answer += f"\nСчёт: {account.name} · {account.currency}"
        elif accounts:
            answer += "\nВыберите счёт командой /accounts."
        else:
            answer += "\nВ этом пространстве пока нет счетов — создайте счёт в Aurum."
        return answer

    async def send_account_picker(
        self,
        client: httpx.AsyncClient,
        chat_id: int,
        telegram_user_id: int,
        *,
        prompt: str = "Выберите счёт для быстрых транзакций",
    ) -> None:
        async with AsyncSessionLocal() as session:
            linked = await self.linked_context(session, telegram_user_id)
            if linked is None:
                await self.send(client, chat_id, "Сначала привяжите аккаунт командой /link КОД.")
                return
            identity, _user, _membership, workspace = linked
            accounts = list(
                (
                    await session.execute(
                        select(Account)
                        .where(Account.workspace_id == workspace.id, Account.is_archived.is_(False))
                        .order_by(Account.id)
                    )
                ).scalars()
            )
            selected_id = identity.default_account_id
        if not accounts:
            await self.send(
                client,
                chat_id,
                f"В пространстве «{workspace.display_name}» нет активных счетов. Сменить пространство: /space",
                open_app=True,
            )
            return
        rows = []
        for account in accounts:
            marker = "✓ " if account.id == selected_id else ""
            rows.append([{
                "text": f"{marker}{account.name} · {account.currency}"[:64],
                "callback_data": f"acct:{account.id}",
            }])
        await self.api(client, "sendMessage", {
            "chat_id": chat_id,
            "text": f"{prompt} в пространстве «{workspace.display_name}»:",
            "reply_markup": {"inline_keyboard": rows},
        })

    async def draft_from_message(self, client: httpx.AsyncClient, chat_id: int, sender_id: int, text: str) -> bool:
        parsed = parse_quick_transaction(text)
        if parsed is None:
            return False
        tx_type, amount, description = parsed
        async with AsyncSessionLocal() as session:
            linked = await self.linked_context(session, sender_id)
            if linked is None:
                await self.send(client, chat_id, "Сначала привяжите аккаунт командой /link КОД.")
                return True
            identity, user, membership, workspace = linked
            if workspace.status == WorkspaceStatus.BLOCKED:
                await self.send(
                    client,
                    chat_id,
                    f"Пространство «{workspace.display_name}» заблокировано администратором. Выберите другое: /space",
                )
                return True
            if membership.role == WorkspaceRole.VIEWER:
                await self.send(
                    client,
                    chat_id,
                    f"В пространстве «{workspace.display_name}» у вас только просмотр. Выберите другое: /space",
                )
                return True
            accounts = list((
                await session.execute(
                    select(Account)
                    .where(Account.workspace_id == workspace.id, Account.is_archived.is_(False))
                    .order_by(Account.id)
                )
            ).scalars())
            if not accounts:
                await self.send(client, chat_id, "Сначала создайте активный счёт в Aurum.", open_app=True)
                return True
            account = next(
                (item for item in accounts if item.id == identity.default_account_id),
                None,
            )
            if account is None and len(accounts) == 1:
                account = accounts[0]
                identity.default_account_id = account.id
            if account is None:
                await self.send_account_picker(
                    client,
                    chat_id,
                    sender_id,
                    prompt="Сначала выберите счёт, затем отправьте транзакцию ещё раз",
                )
                return True
            draft = TelegramTransactionDraft(
                identity_id=identity.id,
                user_id=user.id,
                workspace_id=workspace.id,
                account_id=account.id,
                transaction_type=tx_type.value,
                amount=amount,
                description=description,
                transaction_date=datetime.now(UTC).date(),
                expires_at=datetime.now(UTC) + timedelta(minutes=10),
            )
            session.add(draft)
            await session.commit()
            await session.refresh(draft)
        kind = "Расход" if tx_type == TransactionType.EXPENSE else "Доход"
        payload = {
            "chat_id": chat_id,
            "text": (
                f"{kind}: {amount} {account.currency}\n{description}\n"
                f"Пространство: {workspace.display_name}\nСчёт: {account.name}\n\n"
                "Записать транзакцию? Сменить: /space или /accounts"
            ),
            "reply_markup": {"inline_keyboard": [[
                {"text": "✅ Записать", "callback_data": f"tx:{draft.id.hex}:ok"},
                {"text": "Отмена", "callback_data": f"tx:{draft.id.hex}:no"},
            ]]},
        }
        await self.api(client, "sendMessage", payload)
        return True

    async def handle_callback(self, client: httpx.AsyncClient, callback: dict) -> None:
        callback_id = callback.get("id")
        sender = callback.get("from") or {}
        data = str(callback.get("data") or "")
        if not isinstance(callback_id, str) or not isinstance(sender.get("id"), int):
            return
        space_match = re.fullmatch(r"ws:([0-9a-f]{32})", data)
        if space_match is not None:
            answer = await self.select_space(sender["id"], space_match.group(1))
            await self.api(client, "answerCallbackQuery", {"callback_query_id": callback_id, "text": answer[:200]})
            message = callback.get("message") or {}
            chat = message.get("chat") or {}
            if isinstance(chat.get("id"), int) and isinstance(message.get("message_id"), int):
                await self.api(client, "editMessageText", {
                    "chat_id": chat["id"],
                    "message_id": message["message_id"],
                    "text": answer,
                })
            return
        account_match = re.fullmatch(r"acct:(\d+)", data)
        if account_match is not None:
            answer = "Счёт недоступен"
            async with AsyncSessionLocal() as session:
                linked = await self.linked_context(session, sender["id"])
                if linked is not None:
                    identity, _user, _membership, workspace = linked
                    account = (
                        await session.execute(
                            select(Account).where(
                                Account.id == int(account_match.group(1)),
                                Account.workspace_id == workspace.id,
                                Account.is_archived.is_(False),
                            )
                        )
                    ).scalar_one_or_none()
                    if account is not None:
                        identity.default_account_id = account.id
                        await session.commit()
                        answer = f"Выбран счёт: {account.name} · {account.currency}"
            await self.api(client, "answerCallbackQuery", {
                "callback_query_id": callback_id,
                "text": answer[:200],
            })
            message = callback.get("message") or {}
            chat = message.get("chat") or {}
            if isinstance(chat.get("id"), int) and isinstance(message.get("message_id"), int):
                await self.api(client, "editMessageText", {
                    "chat_id": chat["id"],
                    "message_id": message["message_id"],
                    "text": answer,
                })
            return
        match = re.fullmatch(r"tx:([0-9a-f]{32}):(ok|no)", data)
        if match is None:
            return
        answer = "Черновик уже недоступен"
        async with AsyncSessionLocal() as session:
            try:
                draft_id = UUID(hex=match.group(1))
                row = (
                    await session.execute(
                        select(TelegramTransactionDraft, TelegramIdentity, User, WorkspaceMembership, Workspace)
                        .join(TelegramIdentity, TelegramIdentity.id == TelegramTransactionDraft.identity_id)
                        .join(User, User.id == TelegramTransactionDraft.user_id)
                        .join(Workspace, Workspace.id == TelegramTransactionDraft.workspace_id)
                        .join(
                            WorkspaceMembership,
                            (WorkspaceMembership.user_id == User.id)
                            & (WorkspaceMembership.workspace_id == Workspace.id),
                        )
                        .where(
                            TelegramTransactionDraft.id == draft_id,
                            TelegramIdentity.telegram_user_id == sender["id"],
                            TelegramTransactionDraft.consumed_at.is_(None),
                            TelegramTransactionDraft.expires_at > datetime.now(UTC),
                            User.status == UserStatus.ACTIVE,
                            WorkspaceMembership.revoked_at.is_(None),
                            Workspace.status == WorkspaceStatus.ACTIVE,
                        )
                        .with_for_update()
                    )
                ).one_or_none()
                if row is not None:
                    draft, _identity, user, membership, workspace = row
                    draft.consumed_at = datetime.now(UTC)
                    if match.group(2) == "no":
                        answer = "Отменено"
                    elif membership.role == WorkspaceRole.VIEWER:
                        answer = "Нет права на запись"
                    else:
                        context = RequestWorkspace(user=user, workspace=workspace, membership=membership)
                        fields = {
                            "account_id": draft.account_id,
                            "category_id": None,
                            "transfer_account_id": None,
                            "type": TransactionType(draft.transaction_type),
                            "amount": draft.amount,
                            "description": draft.description,
                            "merchant": None,
                            "notes": "Добавлено через Telegram",
                            "date": draft.transaction_date,
                        }
                        fields = await _currency_fields(session, fields, context)
                        await _apply_categorization_rule(session, fields, context)
                        transaction = Transaction(
                            **fields,
                            workspace_id=workspace.id,
                            author_user_id=user.id,
                        )
                        session.add(transaction)
                        await session.flush()
                        answer = f"Записано: транзакция #{transaction.id}"
                    await session.commit()
            except (HTTPException, ValueError):
                await session.rollback()
                answer = "Не удалось записать. Проверьте счёт и курс валюты в Aurum."
        await self.api(client, "answerCallbackQuery", {"callback_query_id": callback_id, "text": answer})
        message = callback.get("message") or {}
        chat = message.get("chat") or {}
        if isinstance(chat.get("id"), int) and isinstance(message.get("message_id"), int):
            await self.api(client, "editMessageText", {
                "chat_id": chat["id"],
                "message_id": message["message_id"],
                "text": answer,
            })

    async def build_summary(self, telegram_user_id: int) -> tuple[DashboardSummary, str] | SummaryUnavailable:
        """Current-month summary of the linked space, or why it is not available."""
        async with AsyncSessionLocal() as session:
            linked = await self.linked_context(session, telegram_user_id)
            if linked is None:
                return SummaryUnavailable("unlinked", "Сначала привяжите аккаунт командой /link КОД.")
            _identity, user, membership, workspace = linked
            if workspace.status == WorkspaceStatus.BLOCKED:
                return SummaryUnavailable(
                    "blocked",
                    f"Пространство «{workspace.display_name}» заблокировано администратором — "
                    "выберите другое командой /space.",
                )
            today = datetime.now(UTC).date()
            context = RequestWorkspace(user=user, workspace=workspace, membership=membership)
            summary = await get_dashboard_summary(session, today.year, today.month, context)
            return summary, workspace.display_name

    async def send_summary(self, client: httpx.AsyncClient, chat_id: int, telegram_user_id: int) -> None:
        result = await self.build_summary(telegram_user_id)
        if isinstance(result, SummaryUnavailable):
            await self.send(client, chat_id, result.text)
            return
        summary, workspace_name = result
        try:
            # No public_data and no is_shared: the figures stay in this private
            # chat, and Telegram protects widget messages from forwarding.
            await self.api(client, "sendWidget", {
                "chat_id": chat_id,
                "html": SUMMARY_WIDGET_HTML,
                "height": SUMMARY_WIDGET_HEIGHT,
                "chat_data": summary_chat_data(summary, workspace_name, datetime.now(UTC), self.webapp_url),
                "caption": summary_caption(summary, workspace_name),
                "allow_queries": True,
            })
        except (httpx.HTTPError, RuntimeError):
            logger.warning("sendWidget failed; falling back to a text summary")
            await self.send(client, chat_id, summary_text(summary, workspace_name), open_app=True)

    async def handle_widget_query(self, client: httpx.AsyncClient, query: dict) -> None:
        """Refresh button inside the summary widget: recompute and replace chat_data."""
        query_id = query.get("id")
        sender = query.get("from") or {}
        chat = query.get("chat") or {}
        message_id = query.get("message_id")
        if not isinstance(query_id, str):
            return
        answer: dict = {"error": "failed"}
        if (
            query.get("data") == "refresh"
            and isinstance(sender.get("id"), int)
            and isinstance(chat.get("id"), int)
            and isinstance(message_id, int)
        ):
            try:
                result = await self.build_summary(sender["id"])
                if isinstance(result, SummaryUnavailable):
                    # Re-checked on every tap, so an unlinked user or a blocked
                    # space gets no figures.
                    answer = {"error": result.code}
                else:
                    summary, workspace_name = result
                    await self.api(client, "editMessageWidgetData", {
                        "chat_id": chat["id"],
                        "message_id": message_id,
                        "chat_data": summary_chat_data(summary, workspace_name, datetime.now(UTC), self.webapp_url),
                    })
                    answer = {"ok": True}
            except Exception:  # noqa: BLE001 - the query must be answered within 15 s regardless
                logger.warning("Widget refresh failed")
        await self.api(client, "answerWidgetQuery", {
            "widget_query_id": query_id,
            "data": json.dumps(answer, separators=(",", ":")),
        })

    async def drop_card_message(self, client: httpx.AsyncClient, chat_id: int, message_id: object) -> None:
        """Delete a message with a card number and warn without echoing it back."""
        if isinstance(message_id, int):
            try:
                await self.api(client, "deleteMessage", {"chat_id": chat_id, "message_id": message_id})
            except (httpx.HTTPError, RuntimeError):
                # Deleting is best effort; the warning below still goes out.
                logger.warning("Could not delete a Telegram message with a card number")
        await self.send(
            client,
            chat_id,
            "Похоже, в сообщении номер банковской карты. Я удалил его и ничего не сохранил. "
            "Не присылайте реквизиты карт в чат.",
        )

    async def handle_message(self, client: httpx.AsyncClient, message: dict) -> None:
        chat = message.get("chat") or {}
        sender = message.get("from") or {}
        text = str(message.get("text") or "").strip()
        # Photos and documents carry their text in caption/caption_entities.
        caption = str(message.get("caption") or "")
        if chat.get("type") != "private" or not isinstance(sender.get("id"), int):
            return
        chat_id = chat.get("id")
        if not isinstance(chat_id, int):
            return
        # Card numbers must never reach a draft, a transaction or the logs.
        if has_bank_card_number(text, message.get("entities")) or has_bank_card_number(
            caption, message.get("caption_entities")
        ):
            await self.drop_card_message(client, chat_id, message.get("message_id"))
            return
        if text.lower().startswith("/link "):
            code = text.split(maxsplit=1)[1]
            async with AsyncSessionLocal() as session:
                identity = await consume_link_code(
                    session,
                    code=code,
                    telegram_user_id=sender["id"],
                    telegram_username=sender.get("username"),
                    hmac_secret=self.hmac_secret,
                )
                if identity is None:
                    await session.rollback()
                    await self.send(client, chat_id, "Код неверный или уже истёк. Создайте новый код в настройках Aurum.")
                    return
                await session.commit()
            linked_text = "Telegram привязан. Можно добавлять транзакции сообщениями."
            if self.webapp_url:
                linked_text += " Mini App открывается без дополнительного пароля."
            await self.send(client, chat_id, linked_text, open_app=True)
            return
        if text.lower().split("@", 1)[0] in {"/space", "/spaces", "/workspace"}:
            await self.send_space_picker(client, chat_id, sender["id"])
            return
        if text.lower().split("@", 1)[0] in {"/accounts", "/account"}:
            await self.send_account_picker(client, chat_id, sender["id"])
            return
        if text.lower().split("@", 1)[0] in {"/summary", "/balance"}:
            await self.send_summary(client, chat_id, sender["id"])
            return
        if await self.draft_from_message(client, chat_id, sender["id"], text):
            return
        await self.send(client, chat_id, await self.help_text(sender["id"]), open_app=True)

    async def help_text(self, telegram_user_id: int) -> str:
        text = (
            "Быстрый ввод: отправьте «-2500 кофе» для расхода или «+500000 зарплата» для дохода.\n"
            "/space — выбрать пространство, /accounts — выбрать счёт, /summary — сводка за месяц."
        )
        async with AsyncSessionLocal() as session:
            linked = await self.linked_context(session, telegram_user_id)
            if linked is None:
                return text + (
                    "\n\nЧтобы привязать аккаунт: откройте Настройки → Telegram в Aurum, "
                    "создайте код и отправьте сюда /link КОД."
                )
            identity, _user, _membership, workspace = linked
            account = await session.get(Account, identity.default_account_id) if identity.default_account_id else None
        if workspace.status == WorkspaceStatus.BLOCKED:
            return text + (
                f"\n\nПространство «{workspace.display_name}» заблокировано администратором — "
                "выберите другое командой /space."
            )
        target = f"\n\nСейчас транзакции записываются в пространство «{workspace.display_name}»"
        if account is not None and account.workspace_id == workspace.id and not account.is_archived:
            target += f", счёт «{account.name} · {account.currency}»."
        else:
            target += ", счёт ещё не выбран (/accounts)."
        return text + target

    async def run(self) -> None:
        offset = 0
        commands_configured = False
        timeout = httpx.Timeout(40, connect=10)
        async with httpx.AsyncClient(timeout=timeout) as client:
            while True:
                try:
                    if not commands_configured:
                        # Long polling and webhooks are mutually exclusive in
                        # Bot API. Keep pending messages when switching an
                        # existing bot back to this self-hosted worker.
                        await self.api(client, "deleteWebhook", {"drop_pending_updates": False})
                        await self.api(client, "setMyCommands", {"commands": [
                            {"command": "space", "description": "Выбрать пространство для транзакций"},
                            {"command": "accounts", "description": "Выбрать счёт для транзакций"},
                            {"command": "summary", "description": "Сводка за месяц"},
                            {"command": "start", "description": "Помощь и запуск Aurum"},
                        ]})
                        if self.webapp_url:
                            await self.api(client, "setChatMenuButton", {
                                "menu_button": {
                                    "type": "web_app",
                                    "text": "Открыть Aurum",
                                    "web_app": {"url": self.webapp_url},
                                }
                            })
                        commands_configured = True
                    body = await self.api(
                        client,
                        "getUpdates",
                        {
                            "offset": offset,
                            "timeout": 30,
                            "allowed_updates": ["message", "callback_query", "widget_query"],
                        },
                    )
                    for update in body.get("result", []):
                        offset = max(offset, int(update["update_id"]) + 1)
                        if "message" in update:
                            await self.handle_message(client, update["message"])
                        elif "callback_query" in update:
                            await self.handle_callback(client, update["callback_query"])
                        elif "widget_query" in update:
                            await self.handle_widget_query(client, update["widget_query"])
                except (httpx.HTTPError, RuntimeError, KeyError, ValueError):
                    # Never log the exception or request URL: Bot API URLs
                    # contain the token.
                    logger.error("Telegram polling failed; retrying")
                    await asyncio.sleep(5)


async def main() -> None:
    await TelegramBot().run()


if __name__ == "__main__":
    asyncio.run(main())
