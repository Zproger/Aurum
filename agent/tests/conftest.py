"""Shared fixtures and test doubles: config, mock client, scripted model."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import PrivateAttr

from aurum_agent.api_client import AurumClient
from aurum_agent.config import AgentConfig


class ScriptedModel(BaseChatModel):
    """Test double: returns queued AIMessages, records every invocation.

    bind_tools is a no-op — the graph only needs the model to replay
    whatever tool_calls the test scripted. Shared between the graph
    tests and the REPL tests (a scripted REPL session needs a scripted
    model behind it).
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


@pytest.fixture
def aurum_config() -> AgentConfig:
    """A config pointing at a fictional instance; no .env is read."""
    return AgentConfig(
        api_url="http://test.local/api",
        api_user=None,
        api_password=None,
        llm_base_url="https://llm.local/v1",
        llm_model="test-model",
        llm_api_key="test-key",
    )


@pytest.fixture
def mock_client_factory(
    aurum_config: AgentConfig,
) -> Callable[[Callable[[httpx.Request], httpx.Response]], tuple[AurumClient, list[httpx.Request]]]:
    """Build an ``AurumClient`` over a recording ``MockTransport``.

    The handler answers each request with canned JSON; every request is
    captured so tests can assert on method, path, params and body.
    """

    def make(
        handler: Callable[[httpx.Request], httpx.Response],
    ) -> tuple[AurumClient, list[httpx.Request]]:
        calls: list[httpx.Request] = []

        def recording(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return handler(request)

        client = AurumClient(aurum_config, transport=httpx.MockTransport(recording))
        return client, calls

    return make
