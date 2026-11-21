"""Agent configuration: where the Aurum API lives and which LLM to call.

Everything is read from environment variables; the project-root ``.env``
(the same file the Docker stack reads) is picked up automatically, so the
agent is configured where the rest of the instance is. Real environment
variables always win over ``.env`` values (``load_dotenv(override=False)``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# The agent goes through nginx like any other HTTP client (the backend
# container publishes no port to the host), so the default is the web
# container's loopback address from docker-compose.yml.
DEFAULT_API_URL = "http://localhost:3000/api"

# Any OpenAI-compatible endpoint works. The defaults point at Z.ai — the
# vendor of the GLM models this agent was tested with. OpenRouter is a
# drop-in alternative (see agent/README.md for both).
DEFAULT_LLM_BASE_URL = "https://api.z.ai/api/paas/v4/"
DEFAULT_LLM_MODEL = "glm-5.3-flash"


class ConfigError(Exception):
    """Configuration problem with a message that tells the user what to fix."""


def find_env_file(start: Path | None = None) -> Path | None:
    """Look for a ``.env`` from the start directory up to the filesystem root.

    The agent is usually launched from the project root, but walking up
    lets it also run from nested directories (and from the worktree root
    after ``git worktree add``). Note the walk is not bounded by the
    project: without a local ``.env`` it can pick up any parent directory's
    ``.env`` (e.g. ``$HOME/.env``). The ``AURUM_AGENT_`` prefix makes
    accidental collisions unlikely, and callers that need certainty pass
    ``env_file`` explicitly.
    """

    directory = (start or Path.cwd()).resolve()
    for candidate in [directory, *directory.parents]:
        env_path = candidate / ".env"
        if env_path.is_file():
            return env_path
    return None


@dataclass(frozen=True)
class AgentConfig:
    """Validated agent settings; secrets live only in env vars, never in code."""

    api_url: str
    api_user: str | None
    api_password: str | None
    llm_base_url: str
    llm_model: str
    llm_api_key: str


def load_config(env_file: Path | None = None) -> AgentConfig:
    """Collect the config from the environment and the discovered ``.env``.

    The LLM API key is the only required value — without it there is
    nothing to talk to. Everything else has a sane default.
    """
    # Explicit path wins; otherwise the .env is searched for from cwd
    # upward (see find_env_file). Guarding the call keeps dotenv from
    # silently repeating that search itself with load_dotenv(None).
    env_path = env_file or find_env_file()
    if env_path:
        load_dotenv(env_path, override=False)

    # The one hard requirement. Named in the error so the user knows
    # exactly which line to add to .env.
    api_key = (os.getenv("AURUM_AGENT_LLM_API_KEY") or "").strip()
    if not api_key:
        raise ConfigError(
            "AURUM_AGENT_LLM_API_KEY не задан — единственное обязательное "
            "значение. Получите ключ у провайдера модели (Z.ai: z.ai → API Keys; "
            "OpenRouter: openrouter.ai/settings/keys) и добавьте его в корневой .env."
        )

    # Basic auth is a login+password pair: half of it is almost certainly
    # a .env editing mistake, and failing here beats a cryptic 401 later.
    api_user = (os.getenv("AURUM_AGENT_API_USER") or "").strip() or None
    api_password = (os.getenv("AURUM_AGENT_API_PASSWORD") or "").strip() or None
    if (api_user is None) != (api_password is None):
        raise ConfigError(
            "AURUM_AGENT_API_USER и AURUM_AGENT_API_PASSWORD должны быть заданы "
            "вместе — basic auth требует пару логин и пароль. Заполните оба "
            "значения или очистите оба в корневом .env."
        )

    # ``os.getenv(name, default)`` returns a blank string when the variable
    # is set but empty (a typical ``AURUM_AGENT_API_URL=`` line in .env), so
    # defaults are applied with ``or`` instead. Paths are normalized:
    # whitespace stripped, no trailing slash (paths append "/accounts").
    return AgentConfig(
        api_url=(os.getenv("AURUM_AGENT_API_URL") or DEFAULT_API_URL)
        .strip()
        .rstrip("/"),
        api_user=api_user,
        api_password=api_password,
        llm_base_url=(os.getenv("AURUM_AGENT_LLM_BASE_URL") or DEFAULT_LLM_BASE_URL).strip(),
        llm_model=(os.getenv("AURUM_AGENT_LLM_MODEL") or DEFAULT_LLM_MODEL).strip(),
        llm_api_key=api_key,
    )
