"""Graph flow tests with a scripted model: confirmations, refusals, dedup.

The model is a test double that replays queued AIMessages; the API
client is a recording MockTransport. Every scenario walks the real
StateGraph — router, confirm node, interrupt/resume — the way the REPL
will.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from pydantic import PrivateAttr

from aurum_agent.graph import DECLINED_TOOL_RESULT, PENDING_KEY, build_agent_graph
from aurum_agent.tools import build_tools

SYSTEM_PROMPT = "SYS-PROMPT"


class ScriptedModel(BaseChatModel):
    """Test double: returns queued AIMessages, records every invocation.

    bind_tools is a no-op — the graph only needs the model to replay
    whatever tool_calls the test scripted.
    """

    _responses: list[AIMessage] = PrivateAttr(default_factory=list)
    _invocations: list[list[Any]] = PrivateAttr(default_factory=list)

    def queue(self, message: AIMessage) -> None:
        """Schedule the next answer the graph will get from the model."""
        self._responses.append(message)

    @property
    def invocations(self) -> list[list[Any]]:
        """What the graph sent the model on each agent-node run."""
        return self._invocations

    def bind_tools(self, tools: Any, **kwargs: Any) -> ScriptedModel:
        return self

    @property
    def _llm_type(self) -> str:
        return "scripted-test-model"

    def _generate(
        self,
        messages: list[Any],
        stop: Any = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        self._invocations.append(list(messages))
        response = self._responses.pop(0) if self._responses else AIMessage(content="(конец)")
        return ChatResult(generations=[ChatGeneration(message=response)])

    async def _agenerate(
        self,
        messages: list[Any],
        stop: Any = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._generate(messages, stop, run_manager, **kwargs)


async def _no_duplicates(**_: Any) -> list[dict[str, Any]]:
    """Default duplicate checker for scenarios that don't test dedup."""
    return []


def tool_call(call_id: str, name: str, args: dict[str, Any]) -> AIMessage:
    """A model message asking for one tool call."""
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}],
    )


def make_graph(client: httpx.AsyncClient, model: ScriptedModel, dup: Any = None) -> Any:
    bundle = build_tools(client)
    return build_agent_graph(
        model,
        bundle,
        system_prompt=SYSTEM_PROMPT,
        duplicate_checker=dup or _no_duplicates,
        checkpointer=InMemorySaver(),
    )


CONFIG = {"configurable": {"thread_id": "t"}}


async def test_read_only_tool_runs_without_interruption(mock_client_factory: Any) -> None:
    client, calls = mock_client_factory(lambda request: httpx.Response(200, json=[]))
    model = ScriptedModel()
    model.queue(tool_call("c1", "list_accounts", {}))
    model.queue(AIMessage(content="Вот твои счета"))
    graph = make_graph(client, model)

    result = await graph.ainvoke({"messages": [HumanMessage("покажи счета")]}, CONFIG)

    # Reads skip the confirm node entirely.
    assert "__interrupt__" not in result
    assert calls[0].method == "GET"
    assert str(calls[0].url).endswith("/accounts")
    assert result["messages"][-1].content == "Вот твои счета"


async def test_system_prompt_is_prepended_to_every_invocation(
    mock_client_factory: Any,
) -> None:
    client, _ = mock_client_factory(lambda request: httpx.Response(200, json=[]))
    model = ScriptedModel()
    model.queue(AIMessage(content="Привет"))
    graph = make_graph(client, model)

    await graph.ainvoke({"messages": [HumanMessage("привет")]}, CONFIG)

    seen = model.invocations[0]
    assert seen[0].content == SYSTEM_PROMPT
    assert isinstance(seen[1], HumanMessage)


async def test_write_freezes_at_interrupt_and_executes_after_yes(
    mock_client_factory: Any,
) -> None:
    client, calls = mock_client_factory(lambda request: httpx.Response(201, json={"id": 5}))
    model = ScriptedModel()
    model.queue(
        tool_call(
            "c1",
            "create_transaction",
            {
                "account_id": 1,
                "type": "expense",
                "amount": 120.0,
                "description": "Кофе",
                "date": "2026-11-21",
                "category_id": 4,
            },
        )
    )
    model.queue(AIMessage(content="Добавил"))
    graph = make_graph(client, model)

    result = await graph.ainvoke({"messages": [HumanMessage("добавь кофе за 120")]}, CONFIG)

    # The graph stopped before any REST call happened.
    assert "__interrupt__" in result
    assert calls == []
    pending = result["__interrupt__"][0].value[PENDING_KEY]
    assert [entry["name"] for entry in pending] == ["create_transaction"]
    assert pending[0]["args"]["amount"] == 120.0

    result = await graph.ainvoke(Command(resume=[True]), CONFIG)

    assert result["messages"][-1].content == "Добавил"
    assert calls[0].method == "POST"
    assert str(calls[0].url).endswith("/transactions")


async def test_declined_write_never_reaches_the_api(mock_client_factory: Any) -> None:
    client, calls = mock_client_factory(lambda request: httpx.Response(201, json={"id": 5}))
    model = ScriptedModel()
    model.queue(
        tool_call(
            "c1",
            "create_transaction",
            {
                "account_id": 1,
                "type": "expense",
                "amount": 120.0,
                "description": "Кофе",
                "date": "2026-11-21",
            },
        )
    )
    model.queue(AIMessage(content="Хорошо, не добавляю"))
    graph = make_graph(client, model)

    await graph.ainvoke({"messages": [HumanMessage("добавь кофе")]}, CONFIG)
    result = await graph.ainvoke(Command(resume=[False]), CONFIG)

    # Not a single write hit the API; the refusal reached the model as
    # the tool's result, phrased so it will not retry on its own.
    assert calls == []
    tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert tool_messages[0].content == DECLINED_TOOL_RESULT
    # And the model saw it on its next (final) invocation.
    assert any(DECLINED_TOOL_RESULT in str(m.content) for m in model.invocations[1])


async def test_mixed_batch_confirms_only_the_write(
    mock_client_factory: Any,
) -> None:
    # One model turn asking for a read AND a write. Only the write is
    # gated, but the whole batch waits: reads run after the resume too,
    # one batch — one gate.
    client, calls = mock_client_factory(lambda request: httpx.Response(200, json=[]))
    model = ScriptedModel()
    model.queue(
        AIMessage(
            content="",
            tool_calls=[
                {"name": "list_accounts", "args": {}, "id": "c1", "type": "tool_call"},
                {
                    "name": "delete_account",
                    "args": {"account_id": 3},
                    "id": "c2",
                    "type": "tool_call",
                },
            ],
        )
    )
    model.queue(AIMessage(content="Готово"))
    graph = make_graph(client, model)

    result = await graph.ainvoke({"messages": [HumanMessage("удали счёт 3")]}, CONFIG)

    pending = result["__interrupt__"][0].value[PENDING_KEY]
    assert [entry["name"] for entry in pending] == ["delete_account"]
    assert calls == []  # the read has not run either — one batch, one gate

    result = await graph.ainvoke(Command(resume=[True]), CONFIG)

    methods = [call.method for call in calls]
    assert methods == ["GET", "DELETE"]


async def test_create_transaction_preview_carries_duplicates(
    mock_client_factory: Any,
) -> None:
    async def dup(**_: Any) -> list[dict[str, Any]]:
        return [{"id": 7, "amount": "120.00", "description": "Кофе", "date": "2026-11-21"}]

    client, _ = mock_client_factory(lambda request: httpx.Response(200, json=[]))
    model = ScriptedModel()
    model.queue(
        tool_call(
            "c1",
            "create_transaction",
            {
                "account_id": 1,
                "type": "expense",
                "amount": 120.0,
                "description": "Кофе",
                "date": "2026-11-21",
            },
        )
    )
    model.queue(AIMessage(content="…"))
    graph = make_graph(client, model, dup=dup)

    result = await graph.ainvoke({"messages": [HumanMessage("кофе за 120")]}, CONFIG)

    entry = result["__interrupt__"][0].value[PENDING_KEY][0]
    assert entry["duplicates"][0]["id"] == 7


async def test_malformed_resume_declines_everything(mock_client_factory: Any) -> None:
    client, calls = mock_client_factory(lambda request: httpx.Response(201, json={"id": 5}))
    model = ScriptedModel()
    model.queue(
        tool_call(
            "c1",
            "create_tag",
            {"name": "Test"},
        )
    )
    model.queue(AIMessage(content="Отменено"))
    graph = make_graph(client, model)

    await graph.ainvoke({"messages": [HumanMessage("тег Test")]}, CONFIG)
    # Not a list and not the right length — the safe reading is "no".
    result = await graph.ainvoke(Command(resume="garbage"), CONFIG)

    assert calls == []
    tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert tool_messages[0].content == DECLINED_TOOL_RESULT


async def test_unknown_tool_is_reported_not_fatal(mock_client_factory: Any) -> None:
    client, _ = mock_client_factory(lambda request: httpx.Response(200, json=[]))
    model = ScriptedModel()
    model.queue(tool_call("c1", "no_such_tool", {}))
    model.queue(AIMessage(content="Не знаю такого инструмента"))
    graph = make_graph(client, model)

    result = await graph.ainvoke({"messages": [HumanMessage("что-то странное")]}, CONFIG)

    # No interrupt (the name is not a write), and the model got a
    # readable refusal instead of a crash.
    assert "__interrupt__" not in result
    tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert "Unknown tool" in tool_messages[0].content


async def test_plain_answer_ends_the_turn(mock_client_factory: Any) -> None:
    client, calls = mock_client_factory(lambda request: httpx.Response(200, json=[]))
    model = ScriptedModel()
    model.queue(AIMessage(content="Привет! Чем помочь?"))
    graph = make_graph(client, model)

    result = await graph.ainvoke({"messages": [HumanMessage("привет")]}, CONFIG)

    assert result["messages"][-1].content == "Привет! Чем помочь?"
    assert calls == []
    assert len(model.invocations) == 1


async def test_empty_history_does_not_crash_the_first_turn(
    mock_client_factory: Any,
) -> None:
    # The agent node runs before any [-1] read and appends the model's
    # answer, so even an empty invocation is safe: the router sees at
    # least one message. Pins the module's documented invariant.
    client, _ = mock_client_factory(lambda request: httpx.Response(200, json=[]))
    model = ScriptedModel()
    model.queue(AIMessage(content="Чем помочь?"))
    graph = make_graph(client, model)

    result = await graph.ainvoke({"messages": []}, CONFIG)

    assert result["messages"][-1].content == "Чем помочь?"
    # The system prompt is prepended per invocation, not checkpointed:
    # the model saw it, the history does not store it.
    assert model.invocations[0][0].content == SYSTEM_PROMPT
    assert [type(m).__name__ for m in result["messages"]] == ["AIMessage"]


async def test_approvals_are_cleared_after_the_tools_node(mock_client_factory: Any) -> None:
    client, calls = mock_client_factory(lambda request: httpx.Response(201, json={"id": 5}))
    model = ScriptedModel()
    model.queue(tool_call("c1", "create_tag", {"name": "Test"}))
    model.queue(AIMessage(content="Готово"))
    graph = make_graph(client, model)

    await graph.ainvoke({"messages": [HumanMessage("создай тег Test")]}, CONFIG)
    result = await graph.ainvoke(Command(resume=[True]), CONFIG)

    assert calls[0].method == "POST"
    # Single-use decisions: nothing lingers for the next turn.
    assert result["approvals"] == {}
    assert result["pending_calls"] == []


async def test_duplicate_checker_runs_once_across_interrupt_and_resume(
    mock_client_factory: Any,
) -> None:
    # A resumed node re-runs from the top, so the check lives in
    # prepare (which completes and checkpoints) — never in confirm.
    # One interrupt+resume cycle must cost exactly one duplicate call.
    checker_calls: list[dict[str, Any]] = []

    async def counting_dup(**kwargs: Any) -> list[dict[str, Any]]:
        checker_calls.append(kwargs)
        return []

    client, calls = mock_client_factory(lambda request: httpx.Response(201, json={"id": 5}))
    model = ScriptedModel()
    model.queue(
        tool_call(
            "c1",
            "create_transaction",
            {
                "account_id": 1,
                "type": "expense",
                "amount": 120.0,
                "description": "Кофе",
                "date": "2026-11-21",
            },
        )
    )
    model.queue(AIMessage(content="Добавил"))
    graph = make_graph(client, model, dup=counting_dup)

    await graph.ainvoke({"messages": [HumanMessage("добавь кофе")]}, CONFIG)
    await graph.ainvoke(Command(resume=[True]), CONFIG)

    assert len(checker_calls) == 1
    assert checker_calls[0]["description"] == "Кофе"
    # The write's REST call happened once, too — the whole cycle is
    # single-shot. (No GET here: the checker stub never touches the
    # mock client.)
    assert [call.method for call in calls] == ["POST"]


async def test_two_writes_with_mixed_decisions(mock_client_factory: Any) -> None:
    # The decisions map per call: approving one pending write must not
    # approve its neighbor in the same batch.
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(201, json={"id": 9, "name": "A"})
        return httpx.Response(204)

    client, calls = mock_client_factory(handler)
    model = ScriptedModel()
    model.queue(
        AIMessage(
            content="",
            tool_calls=[
                {"name": "create_tag", "args": {"name": "A"}, "id": "c1", "type": "tool_call"},
                {
                    "name": "delete_account",
                    "args": {"account_id": 3},
                    "id": "c2",
                    "type": "tool_call",
                },
            ],
        )
    )
    model.queue(AIMessage(content="Тег создан, счёт не тронул"))
    graph = make_graph(client, model)

    result = await graph.ainvoke({"messages": [HumanMessage("тег и удалить счёт")]}, CONFIG)
    pending = result["__interrupt__"][0].value[PENDING_KEY]
    assert [entry["name"] for entry in pending] == ["create_tag", "delete_account"]

    result = await graph.ainvoke(Command(resume=[True, False]), CONFIG)

    # First executed, second declined — nothing in between.
    assert [call.method for call in calls] == ["POST"]
    tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert "9" in tool_messages[0].content  # the created tag came back
    assert tool_messages[1].content == DECLINED_TOOL_RESULT


async def test_broken_tool_result_is_reported_not_fatal(mock_client_factory: Any) -> None:
    # A tool that crashes mid-processing (here: the accounts endpoint
    # answering a dict where a list was expected) must surface as a
    # readable ToolMessage and let the dialogue continue.
    client, _ = mock_client_factory(lambda request: httpx.Response(200, json={"oops": True}))
    model = ScriptedModel()
    model.queue(tool_call("c1", "list_accounts", {}))
    model.queue(AIMessage(content="Проблема с ответом сервера, попробуй позже"))
    graph = make_graph(client, model)

    result = await graph.ainvoke({"messages": [HumanMessage("счета")]}, CONFIG)

    assert "__interrupt__" not in result
    tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert "Tool execution failed" in tool_messages[0].content
    assert result["messages"][-1].content == "Проблема с ответом сервера, попробуй позже"


@pytest.mark.parametrize(
    ("tool_name", "expected"),
    [("list_categories", "tools"), ("create_category", "confirm")],
)
async def test_router_split(mock_client_factory: Any, tool_name: str, expected: str) -> None:
    # The router is the gate's placement: reads straight to tools,
    # writes through the confirm node.
    client, _ = mock_client_factory(lambda request: httpx.Response(200, json=[]))
    model = ScriptedModel()
    model.queue(tool_call("c1", tool_name, {"name": "x", "kind": "expense", "color": "#000000"}))
    model.queue(AIMessage(content="…"))
    graph = make_graph(client, model)

    result = await graph.ainvoke({"messages": [HumanMessage("действие")]}, CONFIG)

    assert ("__interrupt__" in result) is (expected == "confirm")
