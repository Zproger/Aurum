"""The LangGraph dialogue graph with terminal confirmations on writes.

One exchange walks agent -> (prepare -> confirm?) -> tools -> agent,
until the model answers without tool calls::

    START -> agent -> [no tool calls] -> END
                 |-> [read-only calls] -> tools -> agent
                 |-> [any write call]   -> prepare -> confirm -> tools -> agent

Preparation and confirmation are separate nodes on purpose: a resumed
interrupt re-executes its node from the top, so any work placed above
``interrupt()`` would run twice. ``prepare`` builds the preview payload
(enriched with likely duplicates for create_transaction) and COMPLETES
— its result is checkpointed once. ``confirm`` does nothing before
``interrupt()`` except read that result, so a resume costs one state
read and zero API calls. The REPL renders the payload, the user
answers, and the decision comes back as a per-call list of booleans.

Declined calls are executed as a refusal ToolMessage instead of their
REST call, so the model cannot smuggle a write past the terminal: the
gate is in the graph, not in the prompt.

Invariant behind the ``[-1]`` reads: the agent node is the graph's
only entry point and always appends exactly one model message, so the
router and the prepare/confirm/tools nodes — all reachable only after
agent has run — always see at least that message, even when the graph
was invoked with an empty history.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, ToolMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.types import interrupt

from .tools import ToolBundle

# The refusal the model reads when the user declines a write. Worded
# as an instruction: the model must ask, not retry. English on
# purpose — everything the model reads is English (prompt, tool
# descriptions, backend messages); the model answers the user in the
# user's language, and raw tool results never reach the terminal.
DECLINED_TOOL_RESULT = (
    "The user declined this operation. Do not retry it or any variant "
    "without a new explicit request — ask what to change instead."
)

# Key of the pending-calls list inside the interrupt payload.
PENDING_KEY = "calls"

# Async callable returning likely duplicates for a transaction about
# to be created; bound to the API client by the caller (see main).
DuplicateChecker = Callable[..., Awaitable[list[dict[str, Any]]]]


class AgentState(MessagesState):
    """Dialogue history plus the confirm nodes' working channels.

    ``pending_calls`` is the preview payload built by prepare (write
    calls only, duplicates included); ``approvals`` maps tool_call ids
    to the user's booleans after confirm. Both are cleared by the
    tools node — reads never appear here, they don't need a gate.
    """

    pending_calls: list[dict[str, Any]]
    approvals: dict[str, bool]


def build_agent_graph(
    model: BaseChatModel,
    bundle: ToolBundle,
    *,
    system_prompt: str,
    duplicate_checker: DuplicateChecker,
    checkpointer: BaseCheckpointSaver,
) -> Any:
    """Assemble the compiled graph from the injected dependencies.

    ``duplicate_checker`` is ``find_duplicates`` bound to the API client
    (or a stub in tests) — the graph itself stays network-light. The
    checkpointer is required, not optional: ``interrupt()`` cannot
    freeze and resume a confirmation without one.
    """
    bound_model = model.bind_tools(bundle.tools)
    tools_by_name = {tool.name: tool for tool in bundle.tools}
    write_names = set(bundle.write_names)
    system_message = SystemMessage(content=system_prompt)

    async def agent_node(state: AgentState) -> dict[str, Any]:
        # The system prompt is prepended per invocation instead of
        # living in the history: it stays out of the checkpoints and
        # cannot drift mid-session.
        response = await bound_model.ainvoke([system_message, *state["messages"]])
        return {"messages": [response]}

    async def prepare_node(state: AgentState) -> dict[str, Any]:
        """Build the preview payload; runs exactly once per batch.

        Completing this node checkpoints the pending list, so the
        duplicate check (an API call) is never repeated on resume.
        """
        last = state["messages"][-1]
        pending: list[dict[str, Any]] = []
        for call in last.tool_calls:
            if call["name"] not in write_names:
                continue
            entry: dict[str, Any] = {
                "id": call["id"],
                "name": call["name"],
                "args": call["args"],
            }
            if call["name"] == "create_transaction":
                # Advisory only: a failing duplicate check degrades to
                # [] inside find_duplicates, so this can only enrich
                # the preview, never block it.
                entry["duplicates"] = await duplicate_checker(
                    date=call["args"].get("date"),
                    amount=call["args"].get("amount"),
                    description=call["args"].get("description"),
                )
            pending.append(entry)
        return {"pending_calls": pending}

    async def confirm_node(state: AgentState) -> dict[str, Any]:
        # Zero work above the interrupt: a resumed run re-executes this
        # node from the top, and everything expensive lives in
        # prepare_node, whose checkpointed result is only read here.
        pending = state.get("pending_calls", [])

        # Freeze here: the first run raises the interrupt to the REPL;
        # the resumed run gets the user's answer as the return value.
        decisions = interrupt({PENDING_KEY: pending})

        # A malformed resume (not a list, wrong length) declines every
        # pending call rather than guessing what was approved.
        if not isinstance(decisions, list) or len(decisions) != len(pending):
            decisions = [False] * len(pending)

        approvals: dict[str, bool] = {}
        for entry, decision in zip(pending, decisions):
            approvals[entry["id"]] = bool(decision)
        return {"approvals": approvals}

    async def tools_node(state: AgentState) -> dict[str, Any]:
        last = state["messages"][-1]
        approvals = state.get("approvals", {})
        results: list[ToolMessage] = []
        for call in last.tool_calls:
            tool = tools_by_name.get(call["name"])
            if tool is None:
                results.append(
                    ToolMessage(
                        content=f"Unknown tool: {call['name']}",
                        tool_call_id=call["id"],
                    )
                )
                continue
            if call["name"] in write_names and not approvals.get(call["id"], False):
                results.append(
                    ToolMessage(content=DECLINED_TOOL_RESULT, tool_call_id=call["id"])
                )
                continue
            try:
                observation = await tool.ainvoke(call["args"])
            except Exception as error:  # noqa: BLE001 — one tool failing must not kill the dialogue
                results.append(
                    ToolMessage(
                        content=f"Tool execution failed: {error!r}",
                        tool_call_id=call["id"],
                    )
                )
                continue
            results.append(ToolMessage(content=str(observation), tool_call_id=call["id"]))
        # Approvals are single-use: model-issued ids never repeat, but
        # clearing both working channels keeps the state honest for the
        # next turn.
        return {"messages": results, "approvals": {}, "pending_calls": []}

    def route_after_agent(state: AgentState) -> str:
        last = state["messages"][-1]
        if not getattr(last, "tool_calls", None):
            return END
        if any(call["name"] in write_names for call in last.tool_calls):
            return "prepare"
        return "tools"

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("prepare", prepare_node)
    graph.add_node("confirm", confirm_node)
    graph.add_node("tools", tools_node)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route_after_agent, ["tools", "prepare", END])
    graph.add_edge("prepare", "confirm")
    graph.add_edge("confirm", "tools")
    graph.add_edge("tools", "agent")
    return graph.compile(checkpointer=checkpointer)
