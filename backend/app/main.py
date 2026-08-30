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
    zenmoney,
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


app = FastAPI(title="Aurum API", version=APP_VERSION, lifespan=lifespan)

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
app.include_router(zenmoney.router, prefix="/api")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
