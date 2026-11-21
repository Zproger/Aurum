"""REPL tests: previews, y/n parsing, and scripted end-to-end sessions.

The line reader and the console are injected, so these drive the same
interrupt/resume path a human at the terminal would — including the
duplicate warning rendering and the /reset thread switch.
"""

from __future__ import annotations

import asyncio
import io
from typing import Any

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from rich.console import Console

from aurum_agent.graph import build_agent_graph
from aurum_agent.repl import describe_call, parse_yes, print_pending, repl_loop
from aurum_agent.tools import build_tools
from conftest import ScriptedModel

SYSTEM_PROMPT = "SYS"


class ScriptedReader:
    """Yields queued lines; EOFError once exhausted — a scripted user."""

    def __init__(self, lines: list[str]) -> None:
        self._lines = list(lines)

    async def __call__(self) -> str:
        if not self._lines:
            raise EOFError
        return self._lines.pop(0)


def make_console() -> tuple[Console, io.StringIO]:
    """A headless rich console writing into a buffer the test can read."""
    buffer = io.StringIO()
    console = Console(
        file=buffer, width=120, force_terminal=False, no_color=True, highlight=False
    )
    return console, buffer


async def _no_duplicates(**_: Any) -> list[dict[str, Any]]:
    return []


def make_graph(client: Any, model: ScriptedModel) -> Any:
    return build_agent_graph(
        model,
        build_tools(client),
        system_prompt=SYSTEM_PROMPT,
        duplicate_checker=_no_duplicates,
        checkpointer=InMemorySaver(),
    )


def create_call(call_id: str = "c1") -> AIMessage:
    """A model turn asking to create the familiar coffee transaction."""
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "create_transaction",
                "args": {
                    "account_id": 1,
                    "type": "expense",
                    "amount": 120.0,
                    "description": "Кофе",
                    "date": "2026-11-21",
                },
                "id": call_id,
                "type": "tool_call",
            }
        ],
    )


def transaction_aware_handler(request: httpx.Request) -> httpx.Response:
    """GET /transactions answers an empty page (the dedup), POST is the write."""
    if request.method == "GET":
        return httpx.Response(200, json={"items": [], "total": 0})
    return httpx.Response(201, json={"id": 5})


def test_describe_call_labels_known_actions() -> None:
    line = describe_call("create_transaction", {"account_id": 1, "amount": 120.0})

    assert line.startswith("Создать транзакцию: account_id=1")
    # The most destructive call keeps its cascade warning in the label.
    assert "вместе со ВСЕМИ" in describe_call("delete_account", {"account_id": 3})


def test_describe_call_passes_unknown_names_through() -> None:
    assert describe_call("future_tool", {"x": 1}) == "future_tool: x=1"


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("y", True),
        ("Y", True),
        ("yes", True),
        (" да ", True),
        ("ДА", True),
        ("n", False),
        ("N", False),
        ("no", False),
        ("нет", False),
        ("", False),
        ("   ", False),
        ("может", None),
        ("yn", None),
    ],
)
def test_parse_yes(answer: str, expected: bool | None) -> None:
    assert parse_yes(answer) is expected


def test_print_pending_renders_duplicate_warning() -> None:
    console, buffer = make_console()
    entry = {
        "name": "create_transaction",
        "args": {"amount": 120.0, "description": "Кофе"},
        "duplicates": [
            {
                "id": 7,
                "date": "2026-11-21",
                "amount": "120.00",
                "description": "Кофе",
                "account_name": "Cash",
            }
        ],
    }

    print_pending(console, entry)

    output = buffer.getvalue()
    assert "Создать транзакцию" in output
    assert "похожая транзакция уже есть" in output
    assert "#7" in output


async def test_full_session_write_approved(mock_client_factory: Any) -> None:
    client, calls = mock_client_factory(transaction_aware_handler)
    model = ScriptedModel()
    model.queue(create_call())
    model.queue(AIMessage(content="Добавил!"))
    console, buffer = make_console()

    await repl_loop(make_graph(client, model), console, ScriptedReader(["добавь кофе за 120", "y", "/exit"]))

    output = buffer.getvalue()
    assert "Создать транзакцию" in output  # the preview was shown
    assert "Добавил!" in output  # the final answer was printed
    methods_and_paths = [(call.method, call.url.path) for call in calls]
    # The write happened exactly once — nothing duplicated on the way.
    # (No dedup GET here: this graph's duplicate checker is a stub.)
    assert methods_and_paths.count(("POST", "/api/transactions")) == 1


async def test_full_session_write_declined(mock_client_factory: Any) -> None:
    client, calls = mock_client_factory(transaction_aware_handler)
    model = ScriptedModel()
    model.queue(create_call())
    model.queue(AIMessage(content="Не добавляю."))
    console, buffer = make_console()

    await repl_loop(make_graph(client, model), console, ScriptedReader(["добавь кофе", "n", "/exit"]))

    # The preview was shown, the model answered — but no write happened.
    output = buffer.getvalue()
    assert "Создать транзакцию" in output
    assert "Не добавляю." in output
    assert ("POST", "/api/transactions") not in [
        (call.method, call.url.path) for call in calls
    ]


async def test_unrecognized_answer_is_reasked(mock_client_factory: Any) -> None:
    client, _ = mock_client_factory(transaction_aware_handler)
    model = ScriptedModel()
    model.queue(create_call())
    model.queue(AIMessage(content="Готово"))
    console, buffer = make_console()

    await repl_loop(
        make_graph(client, model),
        console,
        ScriptedReader(["добавь кофе", "может", "y", "/exit"]),
    )

    output = buffer.getvalue()
    assert "Не понял" in output
    assert "Готово" in output


async def test_reset_clears_history_between_threads(mock_client_factory: Any) -> None:
    client, _ = mock_client_factory(lambda request: httpx.Response(200, json=[]))
    model = ScriptedModel()
    model.queue(AIMessage(content="Ок, привет."))
    model.queue(AIMessage(content="Снова привет."))
    console, buffer = make_console()

    await repl_loop(
        make_graph(client, model),
        console,
        ScriptedReader(["привет", "/reset", "ещё раз привет", "/exit"]),
    )

    output = buffer.getvalue()
    assert "История очищена" in output
    assert "Снова привет." in output
    # The second turn ran on a fresh thread: the model saw only the
    # system prompt and the one new message — no first-turn history.
    second_invocation = model.invocations[1]
    human_messages = [m for m in second_invocation if isinstance(m, HumanMessage)]
    assert [m.content for m in human_messages] == ["ещё раз привет"]


async def test_eof_ends_the_session_cleanly(mock_client_factory: Any) -> None:
    client, _ = mock_client_factory(lambda request: httpx.Response(200, json=[]))
    model = ScriptedModel()
    model.queue(AIMessage(content="Привет."))
    console, buffer = make_console()

    await repl_loop(make_graph(client, model), console, ScriptedReader(["привет"]))

    # The reader ran dry (Ctrl-D for a human): a goodbye, no exception.
    assert "Пока!" in buffer.getvalue()


async def test_eof_at_confirmation_prompt_ends_session(mock_client_factory: Any) -> None:
    # Ctrl-D while a y/n question is open must not leak an EOFError
    # traceback; the session ends the same way as at the input prompt —
    # and the pending write never happens.
    client, calls = mock_client_factory(transaction_aware_handler)
    model = ScriptedModel()
    model.queue(create_call())
    console, buffer = make_console()

    await repl_loop(make_graph(client, model), console, ScriptedReader(["добавь кофе"]))

    assert "Пока!" in buffer.getvalue()
    assert ("POST", "/api/transactions") not in [
        (call.method, call.url.path) for call in calls
    ]


async def test_cancellation_at_confirmation_propagates_cleanly(
    mock_client_factory: Any,
) -> None:
    # Ctrl-C in a live event loop arrives as asyncio.CancelledError, not
    # KeyboardInterrupt — the loop prints its message and re-raises for
    # the runner to convert; nothing is written on the way out.
    client, calls = mock_client_factory(transaction_aware_handler)
    model = ScriptedModel()
    model.queue(create_call())

    class CancelAtPrompt:
        """Serves one user line, then simulates Ctrl-C at the y/n prompt."""

        def __init__(self) -> None:
            self._served = False

        async def __call__(self) -> str:
            if not self._served:
                self._served = True
                return "добавь кофе"
            raise asyncio.CancelledError()

    console, buffer = make_console()

    with pytest.raises(asyncio.CancelledError):
        await repl_loop(make_graph(client, model), console, CancelAtPrompt())

    assert "Прервано" in buffer.getvalue()
    assert calls == []  # the turn was cut before any write landed


async def test_one_turn_can_confirm_two_batches(mock_client_factory: Any) -> None:
    # The while-interrupt loop: after the first approval the model may
    # immediately propose another write — each batch gets its own
    # preview and answer, and both writes land exactly once.
    client, calls = mock_client_factory(transaction_aware_handler)
    model = ScriptedModel()
    model.queue(create_call("c1"))
    model.queue(create_call("c2"))
    model.queue(AIMessage(content="Добавил оба."))
    console, buffer = make_console()

    await repl_loop(
        make_graph(client, model),
        console,
        ScriptedReader(["добавь два кофе", "y", "y", "/exit"]),
    )

    output = buffer.getvalue()
    assert output.count("Создать транзакцию") == 2  # two previews, not one
    assert "Добавил оба." in output
    methods_and_paths = [(call.method, call.url.path) for call in calls]
    assert methods_and_paths.count(("POST", "/api/transactions")) == 2


async def test_agent_remembers_previous_turns(mock_client_factory: Any) -> None:
    # Same thread = full memory: on every later turn the model sees the
    # earlier user messages AND its own earlier answers (the checkpointer
    # accumulates them; the agent node replays the whole thread). /reset
    # is the only thing that clears this.
    client, _ = mock_client_factory(lambda request: httpx.Response(200, json=[]))
    model = ScriptedModel()
    model.queue(AIMessage(content="Привет, Миша."))
    model.queue(AIMessage(content="Вспоминаю наш разговор."))
    console, _ = make_console()

    await repl_loop(
        make_graph(client, model),
        console,
        ScriptedReader(["привет, я Миша", "как меня зовут?", "/exit"]),
    )

    second_invocation = model.invocations[1]
    seen_contents = [m.content for m in second_invocation]
    # The full conversation travels with the new question, system
    # prompt first as always.
    assert seen_contents[0] == SYSTEM_PROMPT
    assert "привет, я Миша" in seen_contents  # earlier user message
    assert "Привет, Миша." in seen_contents  # the model's earlier answer
    assert "как меня зовут?" in seen_contents  # the current question
