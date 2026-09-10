"""Audit trail for the handful of operations that destroy or wholesale
replace data.

Aurum is single-user, so this isn't about "who did it" — there's only one
person. It's about *what happened and when*, after the fact. The operations
recorded here are the ones that can't be undone from the UI: restoring a
backup wipes every table before writing the new rows, deleting an account
takes its transactions with it, and a CSV import can add thousands of rows in
one request. When someone opens the app and finds it empty, the container log
is the only place that can say whether a restore ran at 02:14 or whether
something else went wrong.

Deliberately just the standard logger, no table of its own: an audit trail
that lives in the same database it's auditing disappears in exactly the event
it exists to explain (a restore truncates it too). Read it with
`docker compose logs backend`.
"""
import logging

logger = logging.getLogger("aurum.audit")


def log_destructive(action: str, **details: object) -> None:
    """Record one irreversible operation. `details` are rendered as
    key=value; keep them to counts and identifiers — never transaction
    descriptions, amounts or anything else that would spill the user's
    finances into a log file that gets shared when debugging."""
    if details:
        rendered = " ".join(f"{key}={value}" for key, value in details.items())
        logger.warning("%s %s", action, rendered)
    else:
        logger.warning("%s", action)
