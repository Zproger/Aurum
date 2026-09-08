# Contributing to Aurum

Thanks for considering a contribution — code, docs, bug reports, and ideas are all welcome.

## Getting a dev environment running

The fastest path to a working environment is the same Docker Compose setup end users run:

```bash
cp .env.example .env
docker compose up -d --build
```

This gives you Postgres, the FastAPI backend (with migrations applied automatically on boot), and the built frontend served through nginx at `http://localhost:3000`.

For active frontend development with hot reload:

```bash
cd frontend
npm install
npm run dev
```

The dev server proxies API calls to whatever backend is running — point it at the Dockerized backend above, or run the backend locally:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

## Before opening a PR

- **Frontend:** `npm run build` (runs `tsc -b` then `vite build`) must pass with no type errors.
- **Backend:** new tables or columns need an Alembic migration (`alembic revision --autogenerate -m "..."`) — check the generated migration by hand, autogenerate isn't always right.
- **New user-facing text** goes through the translation system in `frontend/src/lib/i18n.ts` (both `ru` and `en` — the `en` object is typed against `ru`'s keys, so a missing translation is a build error, not a runtime surprise) rather than being hardcoded in a component.
- **Mobile:** check your change at a narrow viewport — Aurum is designed mobile-first.
- Keep PRs focused. A bug fix doesn't need an accompanying refactor.

Opening a PR pre-fills this checklist for you — see the [PR template](.github/PULL_REQUEST_TEMPLATE.md).

## Reporting bugs

Open an [Issue](../../issues) with steps to reproduce. For security issues, please use GitHub's private Security tab instead of a public issue.

## Proposing features

Open an [Issue](../../issues) first for anything that changes the data model or adds a new area of the app — it's a lot easier to align on the shape of a feature before code exists than to rework a finished PR.

## License

Aurum is licensed under [PolyForm Noncommercial 1.0.0](LICENSE), not a traditional OSI open source license — see the [README's License section](README.md#-license) for what that means in practice. By submitting a PR, you agree your contribution is licensed under the same terms as the rest of the project.
