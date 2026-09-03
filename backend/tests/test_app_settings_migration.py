"""Regression coverage for configurable currency on a fresh install."""
import importlib.util
from pathlib import Path

import pytest


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "9f3a2d7c5e11_add_app_settings.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("app_settings_migration", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_currency_uses_environment(monkeypatch):
    migration = _load_migration()
    monkeypatch.setenv("AURUM_DEFAULT_CURRENCY", " rub ")

    assert migration._default_currency() == "RUB"


def test_default_currency_falls_back_to_usd(monkeypatch):
    migration = _load_migration()
    monkeypatch.delenv("AURUM_DEFAULT_CURRENCY", raising=False)

    assert migration._default_currency() == "USD"


@pytest.mark.parametrize("currency", ["RU", "RUB1", "РУБ"])
def test_default_currency_rejects_invalid_codes(monkeypatch, currency):
    migration = _load_migration()
    monkeypatch.setenv("AURUM_DEFAULT_CURRENCY", currency)

    with pytest.raises(ValueError, match="three-letter ISO 4217 code"):
        migration._default_currency()
