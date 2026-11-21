"""Shared fixtures: a config and a mock-transport client factory."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from aurum_agent.api_client import AurumClient
from aurum_agent.config import AgentConfig


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
