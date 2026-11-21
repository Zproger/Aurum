"""Entrypoint for the ``aurum-agent`` command: wire everything and run.

The pieces assembled here, in order: config (env + project .env),
the API client (with a pre-flight health check so a missing Docker
stack fails fast with a hint, not with a stack trace), the display
currency for the system prompt, the LLM via any OpenAI-compatible
endpoint, the toolset, the graph with its in-memory checkpointer, and
the REPL. A session lives in one process: the checkpointer is
deliberately in-memory (nothing about the dialogue persists on disk).
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Awaitable, Callable
from datetime import date
from functools import partial
from typing import Any

from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from rich.console import Console

from .api_client import SETTINGS_PATH, AurumApiError, AurumClient
from .config import ConfigError, load_config
from .dedup import find_duplicates
from .graph import build_agent_graph
from .prompts import build_system_prompt
from .repl import ReadLine, repl_loop
from .tools import build_tools


async def _display_currency(client: AurumClient, console: Console) -> str:
    """The instance's display currency for the system prompt.

    A failed settings read degrades to the backend's default — the
    currency is a label for the model, not something to die for.
    """
    try:
        payload = await client.request("GET", SETTINGS_PATH)
    except AurumApiError:
        console.print("[yellow]Не удалось прочитать настройки — валюта по умолчанию: USD.[/yellow]")
        return "USD"
    if isinstance(payload, dict):
        return str(payload.get("currency") or "USD")
    return "USD"


def _make_reader(console: Console) -> ReadLine:
    """Blocking console.input moved off the event loop; EOF ends the session."""

    async def read_line() -> str:
        return await asyncio.to_thread(console.input, "[bold cyan]Вы[/bold cyan] > ")

    return read_line


async def run() -> int:
    """Assemble the agent and hand control to the REPL; 0 on clean exit."""
    try:
        config = load_config()
    except ConfigError as error:
        # Terminal-facing, hence Russian (unlike the model-facing text).
        print(f"Ошибка конфигурации: {error}", file=sys.stderr)
        return 1

    console = Console()
    client = AurumClient(config)
    try:
        if not await client.health():
            console.print(
                f"[red]Aurum недоступен по адресу {config.api_url}.[/red]\n"
                "Проверьте, что стек запущен: docker compose up -d"
            )
            return 1

        currency = await _display_currency(client, console)
        # Any OpenAI-compatible endpoint works (see README): the base
        # URL and the key come from the environment, never from code.
        model = ChatOpenAI(
            model=config.llm_model,
            api_key=config.llm_api_key,
            base_url=config.llm_base_url,
        )
        bundle = build_tools(client)
        graph = build_agent_graph(
            model,
            bundle,
            system_prompt=build_system_prompt(
                today=date.today().isoformat(),
                currency=currency,
            ),
            # The duplicate check rides the same client and inherits
            # its "degrade, never block" failure behavior.
            duplicate_checker=partial(find_duplicates, client),
            # Required for interrupt(): the confirm gate cannot freeze
            # and resume without a checkpointer backing the state.
            checkpointer=InMemorySaver(),
        )
        console.print(
            f"[green]Подключён к Aurum[/green] ({config.api_url}), "
            f"модель: {config.llm_model}"
        )
        await repl_loop(graph, console, _make_reader(console))
    except asyncio.CancelledError:
        # Ctrl-C in a live event loop reaches here as cancellation; the
        # runner turns it back into KeyboardInterrupt once this coroutine
        # lets go, so main() swallows it and the exit stays clean.
        console.print("Пока!")
        raise
    except KeyboardInterrupt:
        # The rare case of the signal landing in a synchronous step
        # (before or after the event loop owns the thread).
        console.print("Пока!")
    finally:
        await client.aclose()
    return 0


def main() -> None:
    """Console-script entrypoint: aurum-agent (also: python -m aurum_agent).

    KeyboardInterrupt here means Ctrl-C: the cancellation was already
    handled (and its message printed) inside run(), so swallow it and
    exit 0 instead of dumping an asyncio traceback.
    """
    try:
        sys.exit(asyncio.run(run()))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
