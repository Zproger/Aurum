"""The terminal REPL: renders confirmation previews, feeds decisions back.

Everything the user actually sees lives here — previews of pending
writes (with duplicate warnings), y/n prompts, the model's answers.
`repl_loop` is deliberately testable: the console and the line reader
are injected, so a scripted session drives the same interrupt/resume
path a human would.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from .graph import PENDING_KEY

# Async line source: returns the next user input, EOFError ends the
# session. Injection keeps the loop testable without a real stdin.
ReadLine = Callable[[], Awaitable[str]]

# Human-readable action labels for the confirmation previews. The
# delete_account label repeats the cascade warning on purpose: it is
# the one operation that destroys other data along with its target.
ACTION_LABELS = {
    "create_transaction": "Создать транзакцию",
    "update_transaction": "Изменить транзакцию",
    "delete_transaction": "Удалить транзакцию",
    "create_account": "Создать счёт",
    "update_account": "Изменить счёт",
    "delete_account": "Удалить счёт — вместе со ВСЕМИ его транзакциями",
    "create_category": "Создать категорию",
    "update_category": "Изменить категорию",
    "delete_category": "Удалить категорию",
    "create_tag": "Создать тег",
}


def describe_call(name: str, args: dict[str, Any]) -> str:
    """One honest line per pending write: the label plus the raw fields.

    Deliberately no name resolution — the preview shows exactly what
    will be sent, and resolving ids to names would cost extra API
    calls before every confirmation.
    """
    label = ACTION_LABELS.get(name, name)
    if not args:
        return label
    details = ", ".join(f"{key}={value!r}" for key, value in args.items())
    return f"{label}: {details}"


def parse_yes(answer: str) -> bool | None:
    """y/yes/д/да → True, n/no/н/нет/empty → False, else None (ask again)."""
    normalized = answer.strip().lower()
    if normalized in {"y", "yes", "д", "да"}:
        return True
    if normalized in {"n", "no", "н", "нет", ""}:
        return False
    return None


def print_pending(console: Console, entry: dict[str, Any]) -> None:
    """Render one pending write, duplicate warning included."""
    lines = [describe_call(entry["name"], entry.get("args") or {})]
    duplicates = entry.get("duplicates") or []
    if duplicates:
        lines.append("[yellow]⚠️  Похоже, похожая транзакция уже есть:[/yellow]")
        for dup in duplicates:
            # #id, date, amount, description, account — enough for the
            # user to recognize their own earlier entry.
            lines.append(
                "    #{} от {}: {} «{}» ({})".format(
                    dup.get("id"),
                    dup.get("date"),
                    dup.get("amount"),
                    dup.get("description"),
                    dup.get("account_name") or "?",
                )
            )
    console.print(Panel("\n".join(lines), title="Подтверждение", border_style="yellow"))


async def confirm_one(console: Console, entry: dict[str, Any], read_line: ReadLine) -> bool:
    """Ask y/n for one pending write until the answer parses."""
    print_pending(console, entry)
    while True:
        decision = parse_yes(await read_line())
        if decision is not None:
            return decision
        console.print("Не понял — введите y (да) или n (нет).")


async def repl_loop(graph: Any, console: Console, read_line: ReadLine) -> None:
    """Read — run — confirm — print, until /exit, EOF or Ctrl-C."""
    thread_id = uuid4().hex
    console.print(
        "[bold]Aurum-агент[/bold] — /reset очистит историю, /exit или Ctrl-D — выход."
    )
    while True:
        try:
            text = (await read_line()).strip()
        except (EOFError, StopAsyncIteration):
            console.print("Пока!")
            return
        if not text:
            continue
        if text in {"/exit", "/quit"}:
            console.print("Пока!")
            return
        if text == "/reset":
            # A fresh thread means a fresh checkpoint: the model starts
            # over with no memory of the previous conversation.
            thread_id = uuid4().hex
            console.print("История очищена — начинаем с чистого листа.")
            continue

        config = {"configurable": {"thread_id": thread_id}}
        try:
            result = await graph.ainvoke({"messages": [HumanMessage(content=text)]}, config)
            # One turn may propose writes several times in a row; each
            # interrupted batch is answered before the turn continues.
            while "__interrupt__" in result:
                pending = result["__interrupt__"][0].value[PENDING_KEY]
                decisions = [await confirm_one(console, entry, read_line) for entry in pending]
                result = await graph.ainvoke(Command(resume=decisions), config)
        except asyncio.CancelledError:
            # Ctrl-C in a live event loop arrives HERE as cancellation,
            # not as KeyboardInterrupt — that one is raised by the
            # runner only after this coroutine lets go. Print, then
            # re-raise: the runner converts it back to KeyboardInterrupt
            # for main() to swallow. A half-run turn may leave the
            # thread checkpoint in a shape providers reject — /reset
            # starts a clean one; do not claim the history is intact.
            console.print("[red]Прервано — ход отменён.[/red]")
            raise
        except KeyboardInterrupt:
            # The rare case of the signal landing during a synchronous
            # step of the loop; same message, but the session survives.
            console.print("[red]Прервано — ход отменён.[/red]")
            continue
        except EOFError:
            # Ctrl-D at a y/n prompt ends the whole session, not just
            # the pending question — the same rule as Ctrl-D at input.
            console.print("Пока!")
            return
        except Exception as error:  # noqa: BLE001 — one bad turn must not kill the session
            # E.g. a provider rejecting a turn shaped by an earlier
            # cancellation; the next /reset always heals.
            console.print(f"[red]Ошибка хода: {error!r}[/red]")
            console.print("Если повторяется — /reset начнёт с чистого листа.")
            continue

        last_message = result["messages"][-1]
        # A tool-only turn cannot END the graph, but an empty answer
        # still prints nothing rather than an empty markdown block.
        if isinstance(last_message, AIMessage) and last_message.content:
            content = last_message.content
            if not isinstance(content, str):
                # Some providers send block lists instead of plain
                # strings; keep the text parts, drop the rest.
                content = " ".join(
                    str(block.get("text", "")) for block in content if isinstance(block, dict)
                )
            if content.strip():
                console.print(Markdown(content))
