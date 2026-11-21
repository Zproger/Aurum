# Aurum Agent

A terminal AI assistant for a running [Aurum](../README.md) instance. It talks
to the instance's REST API (see [DOCS.md](../DOCS.md)) the same way any other
HTTP client does — no direct database access, no extra backend. The scope of
this MVP is **block 1: finance management** — transactions, accounts,
categories and tags: create, edit, search.

```
$ aurum-agent
Подключён к Aurum (http://localhost:3000/api), модель: glm-5.3-flash
Вы > потратил 340 на продукты с карты
Подтверждение
╭──────────────────────────────────────────────────╮
│ Создать транзакцию: account_id=2, type='expense',│
│ amount=340.0, description='Продукты', …          │
╰──────────────────────────────────────────────────╯
Вы > y
Записал: расход 340.00, Продукты, 2026-11-21.
```

## How it works

- **LangChain tools** wrap the REST endpoints — 15 of them: accounts
  (list/create/update/delete), categories (list/create/update/delete),
  tags (list/create), transactions (get/search/create/update/delete).
- **LangGraph** drives the dialogue. Every tool that mutates data is routed
  through a terminal confirmation (`interrupt`/`resume`) — the model cannot
  execute a write without an explicit `y` from you. Declined operations come
  back to the model as a refusal, with an instruction not to retry on its own.
- **Idempotency.** The API has no idempotency keys, so the agent guards
  itself: writes are never auto-retried (a timed-out POST is not re-sent),
  and before creating a transaction the agent checks for an existing one
  with the same date, amount and description — a match shows up as a
  "possible duplicate" warning in the confirmation preview.
- **Memory.** The agent remembers the whole session: your messages, its own
  answers and every tool result. `/reset` starts a clean thread. Memory lives
  in the process (in-memory checkpointer) — a fresh `aurum-agent` run starts
  a fresh conversation.
- The model answers in your language (Russian by default); internal
  prompts, tool descriptions and API messages are English — the model
  handles the translation.

## Setup

Requirements: Python 3.11+ and a running Aurum stack
(`docker compose up -d` in the repo root — the agent checks the instance is
reachable before starting).

```bash
python3 -m venv agent/.venv
agent/.venv/bin/pip install -e ./agent
agent/.venv/bin/aurum-agent          # or: agent/.venv/bin/python -m aurum_agent
```

## Configuration

The `.env` file is discovered from your current directory upward (the
project root being the common case); real environment variables win over
`.env` values. See [.env.example](../.env.example) for the commented
template.

| Variable | Default | Meaning |
|---|---|---|
| `AURUM_AGENT_LLM_API_KEY` | — | **Required.** The LLM provider's key. |
| `AURUM_AGENT_LLM_BASE_URL` | `https://api.z.ai/api/paas/v4/` | Any OpenAI-compatible API endpoint. |
| `AURUM_AGENT_LLM_MODEL` | `glm-5.3-flash` | Model id at that endpoint. |
| `AURUM_AGENT_API_URL` | `http://localhost:3000/api` | Your running instance (through nginx). |
| `AURUM_AGENT_API_USER` / `_PASSWORD` | empty | Fill only if basic auth is enabled on the instance — the same pair the web UI asks for. |

### Where to get the base URL and the key

The agent works with any OpenAI-compatible endpoint. The defaults point at
Z.ai — the vendor of the GLM model family this agent was tested with.

| Provider | Base URL | Model id | Key |
|---|---|---|---|
| **Z.ai** (direct) | `https://api.z.ai/api/paas/v4/` | `glm-5.3-flash` | [z.ai → API Keys](https://z.ai/manage-apikey/apikey-list). GLM Coding Plan subscribers must use their dedicated endpoint (`https://api.z.ai/api/coding/paas/v4`) instead of the general one. |
| **OpenRouter** | `https://openrouter.ai/api/v1` | `z-ai/glm-5.3-flash` (note the prefix) | [openrouter.ai/settings/keys](https://openrouter.ai/settings/keys) |
| **Ollama** (local) | `http://localhost:11434/v1` | whatever you pulled | no real key exists — set `AURUM_AGENT_LLM_API_KEY` to any non-empty placeholder. Any OpenAI-compatible local server works. |

GLM-5.3-flash supports function calling (which the whole toolset relies on)
and costs cents per session of terminal use.

## In the terminal

- `y` / `yes` / `д` / `да` — approve a pending write; `n` / `no` / `н` /
  `нет` / empty — decline it. The answer is typed at the regular prompt,
  right under the preview panel; each write in a batch is asked
  separately, and an unrecognized answer is re-asked.
- `/reset` — forget the conversation and start a new thread.
- `/exit` or `/quit`, or `Ctrl-D`, ends the session cleanly. `Ctrl-C`
  during a running turn cancels the turn and also ends the session —
  an interrupted confirmation never writes anything; if the next run's
  model acts oddly after an interrupted mid-turn confirmation, start
  it with a fresh conversation (memory is per-process anyway).

## Tests

```bash
cd agent && .venv/bin/python -m pytest
```

The suite (128 tests) runs without a running instance, an LLM, or network
access: the API is a recording `MockTransport`, the model is a scripted test
double that replays queued answers through the real graph.

## Not in this MVP (on purpose)

- Transaction splits across categories (single-category rows only).
- Budgets, goals, assets, crypto, recurring — later blocks.
- `DELETE /tags/{id}` — the agent creates and lists tags, it does not manage
  the tag dictionary.
- Cross-restart memory persistence (SQLite checkpointer) and streaming
  output — natural follow-ups.
