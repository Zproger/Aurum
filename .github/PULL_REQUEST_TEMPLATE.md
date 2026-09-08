## What does this change, and why?

<!-- The "why" matters more than the "what" here — what problem does this
     solve, or what couldn't you do before this change? If it fixes a bug,
     what's the concrete repro? -->

## Checklist

- [ ] I actually ran `npm run build` (frontend) and/or `pytest` (backend) locally, not just assumed it would pass.
- [ ] If this adds/changes tests, I ran them and watched them pass — not just wrote assertions that look right.
- [ ] New/changed table or column → included an Alembic migration (see [CONTRIBUTING.md](../CONTRIBUTING.md#before-opening-a-pr)).
- [ ] New user-facing text is in `frontend/src/lib/i18n.ts` for **both** `ru` and `en`, not hardcoded.
- [ ] If this touches the UI, I checked it at a narrow (mobile) viewport, not just desktop.
- [ ] No personal/financial data, credentials, or API keys anywhere in the diff — screenshots included, if any.
- [ ] This PR does one thing. Unrelated fixes/refactors/formatting are split into separate PRs.

## Screenshots / output

<!-- For a UI change: before/after screenshots (desktop + mobile). For a
     backend change: relevant command output (e.g. the test run). -->
