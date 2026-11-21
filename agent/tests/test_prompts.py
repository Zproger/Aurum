"""System prompt tests: session facts and the non-negotiable rules."""

from __future__ import annotations

from aurum_agent.prompts import build_system_prompt


def test_prompt_includes_session_facts() -> None:
    prompt = build_system_prompt(today="2026-11-21", currency="USD")

    assert "Today is 2026-11-21" in prompt
    assert "USD" in prompt


def test_prompt_pins_confirmation_etiquette() -> None:
    prompt = build_system_prompt(today="2026-11-21", currency="RUB")

    # No silent retries of declined writes, and duplicate warnings are
    # the user's call — both are the graph's contracts restated.
    assert "declines" in prompt
    assert "duplicate" in prompt
    assert "never guess" in prompt
