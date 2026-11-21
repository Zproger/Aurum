"""Config loading tests: where values come from and what is validated."""

from __future__ import annotations

from pathlib import Path

import pytest

from aurum_agent.config import (
    DEFAULT_API_URL,
    DEFAULT_LLM_BASE_URL,
    DEFAULT_LLM_MODEL,
    ConfigError,
    find_env_file,
    load_config,
)

AGENT_ENV_VARS = (
    "AURUM_AGENT_API_URL",
    "AURUM_AGENT_API_USER",
    "AURUM_AGENT_API_PASSWORD",
    "AURUM_AGENT_LLM_BASE_URL",
    "AURUM_AGENT_LLM_MODEL",
    "AURUM_AGENT_LLM_API_KEY",
)


@pytest.fixture(autouse=True)
def clean_agent_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep ambient shell variables and earlier tests' .env leakage out."""
    for name in AGENT_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_find_env_file_walks_up_the_tree(tmp_path: Path) -> None:
    # The .env sits two levels above the start directory, as it does when
    # the agent is launched from a nested project directory.
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    (tmp_path / ".env").write_text("AURUM_AGENT_LLM_API_KEY=x", encoding="utf-8")

    assert find_env_file(nested) == tmp_path / ".env"


def test_find_env_file_returns_none_without_file(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    assert find_env_file(tmp_path / "a") is None


def test_load_config_reads_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".env").write_text(
        "AURUM_AGENT_LLM_API_KEY=file-key\n"
        "AURUM_AGENT_LLM_MODEL=file-model\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    config = load_config()

    assert config.llm_api_key == "file-key"
    assert config.llm_model == "file-model"


def test_real_env_overrides_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Same precedence as the Docker stack: what's already in the
    # environment wins over what the .env file says.
    (tmp_path / ".env").write_text(
        "AURUM_AGENT_LLM_API_KEY=file-key\n"
        "AURUM_AGENT_LLM_MODEL=file-model\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AURUM_AGENT_LLM_MODEL", "env-model")

    config = load_config()

    assert config.llm_api_key == "file-key"
    assert config.llm_model == "env-model"


def test_defaults_apply_when_only_key_is_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AURUM_AGENT_LLM_API_KEY", "k")

    config = load_config()

    assert config.api_url == DEFAULT_API_URL
    assert config.api_user is None
    assert config.api_password is None
    assert config.llm_base_url == DEFAULT_LLM_BASE_URL
    assert config.llm_model == DEFAULT_LLM_MODEL


def test_missing_llm_key_is_a_config_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ConfigError, match="AURUM_AGENT_LLM_API_KEY"):
        load_config()


def test_blank_basic_auth_becomes_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AURUM_AGENT_LLM_API_KEY", "k")
    monkeypatch.setenv("AURUM_AGENT_API_USER", "   ")
    monkeypatch.setenv("AURUM_AGENT_API_PASSWORD", "")

    config = load_config()

    assert config.api_user is None
    assert config.api_password is None


def test_basic_auth_values_pass_through(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AURUM_AGENT_LLM_API_KEY", "k")
    monkeypatch.setenv("AURUM_AGENT_API_USER", "misha")
    monkeypatch.setenv("AURUM_AGENT_API_PASSWORD", "secret")

    config = load_config()

    assert config.api_user == "misha"
    assert config.api_password == "secret"


def test_api_url_trailing_slash_is_stripped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Paths are appended as "/accounts", so a trailing slash would double up.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AURUM_AGENT_LLM_API_KEY", "k")
    monkeypatch.setenv("AURUM_AGENT_API_URL", "http://localhost:3000/api/")

    config = load_config()

    assert config.api_url == "http://localhost:3000/api"


def test_blank_env_values_fall_back_to_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A blank "AURUM_AGENT_API_URL=" line in .env is a common edit — it
    # must mean "use the default", not "use an empty string".
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AURUM_AGENT_LLM_API_KEY", "k")
    monkeypatch.setenv("AURUM_AGENT_API_URL", "")
    monkeypatch.setenv("AURUM_AGENT_LLM_BASE_URL", "")
    monkeypatch.setenv("AURUM_AGENT_LLM_MODEL", "")

    config = load_config()

    assert config.api_url == DEFAULT_API_URL
    assert config.llm_base_url == DEFAULT_LLM_BASE_URL
    assert config.llm_model == DEFAULT_LLM_MODEL


def test_llm_key_whitespace_is_stripped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AURUM_AGENT_LLM_API_KEY", "  key  ")

    config = load_config()

    assert config.llm_api_key == "key"


def test_half_filled_basic_auth_is_a_config_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Basic auth is a login+password pair; half of it is a .env mistake
    # that would otherwise surface as a cryptic 401 from the API client.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AURUM_AGENT_LLM_API_KEY", "k")
    monkeypatch.setenv("AURUM_AGENT_API_USER", "misha")

    with pytest.raises(ConfigError, match="AURUM_AGENT_API_USER"):
        load_config()


def test_half_filled_basic_auth_password_only_is_a_config_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AURUM_AGENT_LLM_API_KEY", "k")
    monkeypatch.setenv("AURUM_AGENT_API_PASSWORD", "secret")

    with pytest.raises(ConfigError, match="AURUM_AGENT_API_USER"):
        load_config()
