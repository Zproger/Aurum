from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    accounts,
    advice,
    assets,
    backup,
    budgets,
    cash_flow,
    categories,
    crypto,
    dashboard,
    goals,
    insights,
    net_worth,
    recurring,
    reports,
    settings as settings_routes,
    tags,
    transactions,
)
from app.core.config import APP_VERSION, get_settings
from app.db.seed import seed_default_account, seed_default_app_settings, seed_default_categories
from app.db.session import AsyncSessionLocal

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncSessionLocal() as session:
        await seed_default_categories(session)
        await seed_default_account(session)
        await seed_default_app_settings(session)
    yield


app = FastAPI(
    title="Aurum API",
    version=APP_VERSION,
    lifespan=lifespan,
    # Docs live under /api/* because nginx only proxies that prefix to the
    # backend (see frontend/nginx.conf) — everything else falls through to
    # the SPA's index.html, which is why the defaults (/docs, /openapi.json)
    # would silently 404 through the reverse proxy.
    # All three go away together when AURUM_ENABLE_DOCS=false — leaving
    # openapi.json reachable would keep handing out the full API map even
    # with the Swagger UI itself switched off.
    docs_url="/api/docs" if settings.enable_docs else None,
    redoc_url="/api/redoc" if settings.enable_docs else None,
    openapi_url="/api/openapi.json" if settings.enable_docs else None,
)

# CORS stays off unless someone deliberately opens it, and credentials are
# only granted to a pinned list. Starlette answers a credentialed "*" by
# echoing back whatever Origin asked instead of a literal "*" — so the two
# together turn any page the user happens to have open into an authenticated
# client of their instance, which is exactly what the README's "fine if it's
# only reachable from localhost" advice assumes can't happen.
cors_origins = settings.cors_origins_list
if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials="*" not in cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(dashboard.router, prefix="/api")
app.include_router(accounts.router, prefix="/api")
app.include_router(categories.router, prefix="/api")
app.include_router(transactions.router, prefix="/api")
app.include_router(assets.router, prefix="/api")
app.include_router(net_worth.router, prefix="/api")
app.include_router(backup.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(insights.router, prefix="/api")
app.include_router(settings_routes.router, prefix="/api")
app.include_router(budgets.router, prefix="/api")
app.include_router(advice.router, prefix="/api")
app.include_router(goals.router, prefix="/api")
app.include_router(recurring.router, prefix="/api")
app.include_router(cash_flow.router, prefix="/api")
app.include_router(tags.router, prefix="/api")
app.include_router(crypto.router, prefix="/api")


@app.get("/api/health")
async def health() -> dict[str, str]:
    # Status only. This is the one route nginx serves without auth (Docker's
    # HEALTHCHECK and uptime monitors need it — see frontend/nginx.conf), so
    # anything returned here is world-readable. The running version used to
    # ride along, which told an unauthenticated caller exactly which release
    # they were looking at, and therefore which known issues it still has;
    # it now comes back from GET /api/settings, which is behind auth.
    return {"status": "ok"}
