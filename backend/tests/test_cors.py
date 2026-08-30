"""CORS defaults.

The README tells self-hosters that leaving basic auth off is fine as long as
the instance is only reachable from localhost. That promise only holds if a
random page open in the same browser can't call the API on their behalf —
which is what these tests pin down.
"""
from httpx import AsyncClient

from app.core.config import Settings

EVIL = "https://evil.example"


async def test_a_foreign_origin_is_never_echoed_back(client: AsyncClient):
    """Starlette answers a credentialed wildcard by echoing whatever Origin
    asked, which is what makes the wildcard dangerous rather than merely
    permissive — the answer must be `*` or nothing, never the caller's own
    origin."""
    resp = await client.get("/accounts", headers={"Origin": EVIL})

    assert resp.headers.get("access-control-allow-origin") != EVIL


async def test_credentials_are_not_granted_to_every_origin(client: AsyncClient):
    """With allow-credentials, a page the user visits can call the instance
    with their Basic Auth attached and read the response."""
    resp = await client.get("/accounts", headers={"Origin": EVIL})

    assert resp.headers.get("access-control-allow-credentials") != "true"


def test_shipped_default_allows_no_cross_origin_access():
    """Nothing in the shipped setup needs CORS: compose serves UI and API
    from one origin, and the Vite dev server proxies /api. So the default
    should be closed, not `*`."""
    assert Settings.model_fields["cors_origins"].default == ""
