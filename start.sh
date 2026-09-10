#!/bin/sh
# Thin wrapper around `docker compose up` that guarantees a .env file
# exists before containers start. Running `docker compose up --build`
# directly works fine even without .env — every variable in
# docker-compose.yml and backend/app/core/config.py has a hardcoded
# fallback — but that means someone who skips the README's "cp
# .env.example .env" step gets a fully working instance with no visible
# sign that it's running on defaults (weak Postgres password, no basic
# auth — see frontend/docker-entrypoint.d/20-basic-auth.sh) until they
# go looking for it. This script closes that gap: if .env is missing,
# it's created from .env.example and the operator is told, loudly, once,
# before anything starts — rather than staying silent forever.
set -eu

cd "$(dirname "$0")"

if [ ! -f .env ]; then
  cp .env.example .env
  cat >&2 <<'EOF'
[aurum] No .env file found — created one from .env.example with default values:
[aurum]   - No password on the app itself (AURUM_BASIC_AUTH_USER/PASSWORD blank)
[aurum]   - Default Postgres credentials (AURUM_POSTGRES_PASSWORD=change-me)
[aurum] Fine for a quick local try-out on localhost. Before exposing this beyond
[aurum] your own machine, edit .env and re-run this script (or `docker compose up -d --build`).
EOF
fi

exec docker compose up -d --build "$@"
