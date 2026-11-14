"""Bank statement import: parsing, previewing, and the commit that follows.

The pipeline the tests pin down is parse -> preview/edit -> validate -> commit:
nothing is written to the ledger until the user confirms, and re-uploading the
same document adds nothing.
"""
import asyncio
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from openpyxl import Workbook

from app.api.routes import statement_imports as statement_import_routes
from app.services import statement_import_service
from app.importers.freedom_bank import FreedomBankPdfImporter
from app.importers.kaspi import KaspiPdfImporter
from app.importers import kaspi as kaspi_importer
from app.importers.ocr_worker import validate_render_size
from app.schemas.statement_import import StatementPreview
from tests.helpers import money

HEADER = ["Операция №", "Дата", "Операция", "Комментарий", "Сумма", "Валюта"]


def test_ocr_rejects_a_page_that_expands_beyond_the_pixel_limit():
    with pytest.raises(ValueError, match="pixel limit"):
        validate_render_size(20_000, 20_000)


def _workbook(rows: list[list]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "sheet"
    sheet.append(HEADER)
    for row in rows:
        sheet.append(row)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def _tradernet_file() -> bytes:
    return _workbook(
        [
            [101, datetime(2026, 9, 18), "Дивиденды", "Дивиденды по бумаге (Issuer (TEST.KZ))", 1250, "KZT"],
            [102, datetime(2026, 9, 18), "Купон", "Купон по бумаге (Bond (BOND.AIX.KZ))", 10, "USD"],
            [103, datetime(2026, 9, 18), "Блокировка", "Temporary", -10, "USD"],
        ]
    )


def _rate(value: str):
    """A stand-in for the NBK lookup, so the import tests never touch the
    network and the KZT snapshot is a known number."""

    async def lookup(*args, **kwargs):
        return SimpleNamespace(rate_to_kzt=Decimal(value))

    return lookup


async def _preview(client: AsyncClient, content: bytes | None = None):
    return await client.post(
        "/statement-imports/preview", files={"file": ("tradernet.xlsx", content or _tradernet_file())}
    )


async def test_tradernet_preview_recognizes_income_and_ignored_rows(client: AsyncClient):
    response = await _preview(client)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["provider"] == "tradernet"
    assert body["provider_label"] == "Tradernet Global / Freedom Broker"
    assert [row["purpose"] for row in body["rows"][:2]] == ["dividend", "coupon"]
    assert body["rows"][0]["security_symbol"] == "TEST.KZ"
    assert body["rows"][2]["importable"] is False


async def test_preview_writes_nothing_to_the_ledger(client: AsyncClient):
    """The whole point of the preview step: reading a document must not post a
    single transaction."""
    before = (await client.get("/transactions")).json()["total"]

    assert (await _preview(client)).status_code == 200

    assert (await client.get("/transactions")).json()["total"] == before


async def test_excel_serial_dates_are_recognized(client: AsyncClient):
    """The real export writes its date column as a bare Excel serial number
    unless the cell happens to carry a date format. A parser that only accepts
    datetimes skips every row of the actual file instead of failing loudly."""
    content = _workbook([[201, 45247.43127314815, "Дивиденды", "(Issuer (TEST.KZ))", 100, "KZT"]])

    body = (await _preview(client, content)).json()

    assert [row["date"] for row in body["rows"]] == ["2023-11-17"]


async def test_reversed_operation_takes_its_direction_from_the_amount(client: AsyncClient):
    """"Reverted: Купон …" arrives as a negative coupon. Reading the operation
    name alone would book it as income and overstate the balance."""
    content = _workbook([[301, datetime(2026, 9, 18), "Купон", "Reverted: Купон по бумаге", -9, "USD"]])

    body = (await _preview(client, content)).json()

    row = body["rows"][0]
    assert row["type"] == "expense"
    assert row["purpose"] == "coupon"
    assert money(row["amount"]) == Decimal("9")


async def test_unrecognized_document_is_rejected_without_crashing(client: AsyncClient):
    response = await client.post(
        "/statement-imports/preview", files={"file": ("broken.xlsx", b"this is not a workbook")}
    )
    assert response.status_code == 422


async def test_preview_timeout_kills_and_reaps_the_worker_process_group(monkeypatch):
    events: list[object] = []
    spawned: list[object] = []

    class SlowProcess:
        pid = 4321
        returncode = None

        async def communicate(self, content):
            await asyncio.sleep(1)

        async def wait(self):
            events.append("reaped")
            self.returncode = -9

    async def create_process(*args, **kwargs):
        spawned.extend(args)
        return SlowProcess()

    monkeypatch.setattr(statement_import_routes.asyncio, "create_subprocess_exec", create_process)
    monkeypatch.setattr(statement_import_routes.os, "killpg", lambda pid, sig: events.append((pid, sig)))
    monkeypatch.setattr(statement_import_routes, "PREVIEW_TIMEOUT_SECONDS", 0.01)

    with pytest.raises(HTTPException, match="timed out"):
        await statement_import_routes._parse_in_worker("slow.pdf", b"pdf")

    assert events == [(4321, statement_import_routes.signal.SIGKILL), "reaped"]
    assert "-m" not in spawned
    assert str(spawned[1]).endswith("app/importers/statement_preview_worker.py")


async def test_preview_timeout_reaps_worker_if_process_group_already_exited(monkeypatch):
    events: list[str] = []

    class ExitedProcess:
        pid = 4321
        returncode = None

        async def communicate(self, content):
            await asyncio.sleep(1)

        async def wait(self):
            events.append("reaped")
            self.returncode = 0

    async def create_process(*args, **kwargs):
        return ExitedProcess()

    def already_exited(pid, sig):
        raise ProcessLookupError

    monkeypatch.setattr(statement_import_routes.asyncio, "create_subprocess_exec", create_process)
    monkeypatch.setattr(statement_import_routes.os, "killpg", already_exited)
    monkeypatch.setattr(statement_import_routes, "PREVIEW_TIMEOUT_SECONDS", 0.01)

    with pytest.raises(HTTPException, match="timed out"):
        await statement_import_routes._parse_in_worker("slow.pdf", b"pdf")

    assert events == ["reaped"]


async def test_unsupported_file_type_names_what_is_supported(client: AsyncClient):
    response = await client.post("/statement-imports/preview", files={"file": ("statement.csv", b"a,b")})
    assert response.status_code == 422
    assert ".xlsx" in response.json()["detail"]
    assert ".pdf" in response.json()["detail"]


def test_kaspi_text_statement_preserves_fx_purchase_and_reconciles():
    pages = [
        """Kaspi Bank\nВЫПИСКА Kaspi Gold\nДоступно на 17.09.26 + 5 607,35 ₸""",
        """Дата Сумма Операция Детали
18.09.26 - 1 000,00 ₸   Перевод на свой      На Kaspi Депозит
счет
17.09.26 - 200,00 ₸   Разное      Комиссия за перевод на карту др. банка
17.09.26 - 6 000,00 ₸   Перевод      На карту другого банка Super App P2P
17.09.26 + 10 000,00 ₸   Поступление со      С Kaspi Депозита
своего счета
17.09.26 - 1 900,00 ₸   Покупка      YANDEX.GO
17.09.26 + 2 000,00 ₸   Поступление со      С Kaspi Депозита
своего счета
17.09.26 - 1 650,00 ₸   Покупка      Аппарат самообслуживания
17.09.26 - 2 918,98 ₸   Покупка      YANDEX.EDA
(- 19,58 BYN)
17.09.26 - 785,00 ₸   Покупка      Аппарат самообслуживания
- Сумма заблокирована и ожидает списания
Доступно на 18.09.26 + 3 153,37 ₸""",
    ]

    preview = KaspiPdfImporter().parse_pages("kaspi.pdf", pages)

    assert len(preview.rows) == 9
    fx = next(row for row in preview.rows if row.details == "YANDEX.EDA")
    assert fx.account_currency == "KZT"
    assert fx.currency == "BYN"
    assert fx.amount == Decimal("2918.98")
    assert fx.transaction_amount == Decimal("19.58")
    # Own-account transfers stay out; the blocked purchase is already spent.
    assert sum(row.importable for row in preview.rows) == 6
    blocked = preview.rows[-1]
    assert blocked.importable is True
    assert blocked.warning == "Blocked amount awaiting confirmation; imported as spent"
    assert blocked.details == "Аппарат самообслуживания"
    assert preview.warnings == ["Balance check passed: opening balance plus operations equals closing balance"]


def test_kaspi_blocked_marker_after_the_last_row_does_not_leak_into_details():
    """Real 2026 layout: the blocked note sits under the final purchase, right
    before the summary section, and must neither drop the row nor become part
    of its description."""
    pages = [
        "Kaspi Bank\nВЫПИСКА Kaspi Gold\nДоступно на 17.09.26 + 1 000,00 ₸",
        """Дата Сумма Операция Детали
17.09.26 - 100,00 ₸   Покупка      Магазин
17.09.26 - 50,00 ₸   Покупка      Аппарат самообслуживания
- Сумма заблокирована. Банк ожидает подтверждения от платежной системы.
Раздел «Краткое содержание операций по карте» содержит информацию об операциях
Доступно на 18.09.26 + 850,00 ₸""",
    ]

    preview = KaspiPdfImporter().parse_pages("kaspi.pdf", pages)

    assert [row.importable for row in preview.rows] == [True, True]
    assert preview.rows[-1].details == "Аппарат самообслуживания"
    assert preview.rows[-1].warning == "Blocked amount awaiting confirmation; imported as spent"
    assert preview.warnings == ["Balance check passed: opening balance plus operations equals closing balance"]


def _kaspi_ocr_pages(*, closing: str = "1 240,00") -> list[str]:
    """Synthetic, redacted representation of Kaspi's image-text layout.

    Real PDFs of this form have an unusable embedded character map, so local
    Tesseract sees the tenge glyph as T/Т and sometimes reads the pending icon
    as © or ``Sc``. The fixture keeps those OCR artefacts without retaining any
    customer, card, account, or merchant data from an actual statement.
    """

    return [
        "СПРАВКА об остатке на счете",
        f"""ВЫПИСКА
по Kaspi Gold за период с 01.09.26 по 02.09.26
Доступно на 01.09.26 + 1 000,00 T
Дата Сумма Операция Детали
02.09.26 - 100,00 T Покупка © Магазин
02.09.26 + 50,00 T Поступление co Sc Kaspi Депозита
своего счета
02.09.26 - 10,00 T Pa3Hoe Комиссия за перевод
02.09.26 - 200,00 T Покупка Онлайн-сервис
(- 1,00 USD)
02.09.26 + 500,00 T Пополнение Доход
Доступно на 02.09.26 + {closing} T
АО «Kaspi Bank»""",
    ]


def test_kaspi_ocr_layout_preserves_rows_fx_and_pending_markers():
    preview = KaspiPdfImporter().parse_pages("kaspi-ocr.pdf", _kaspi_ocr_pages())

    assert len(preview.rows) == 5
    # The © purchase is blocked but spent; the Sc incoming row is an own-account transfer.
    assert [row.importable for row in preview.rows] == [True, False, True, True, True]
    assert preview.rows[1].description == "Поступление со своего счета"
    assert preview.rows[2].purpose.value == "fee"
    assert preview.rows[3].currency == "USD"
    assert preview.rows[3].transaction_amount == Decimal("1.00")
    assert preview.warnings == ["Balance check passed: opening balance plus operations equals closing balance"]


def test_kaspi_parse_falls_back_to_local_ocr_for_unreadable_text_layer(monkeypatch):
    monkeypatch.setattr(kaspi_importer, "extract_pdf_pages", lambda content: ["ducuhpcyhuh"])
    monkeypatch.setattr(kaspi_importer, "extract_pdf_pages_ocr", lambda content: _kaspi_ocr_pages())

    preview = KaspiPdfImporter().parse("kaspi.pdf", b"pdf")

    assert len(preview.rows) == 5
    assert preview.warnings[0] == "Local OCR was used; review every row before importing"
    assert preview.requires_row_confirmation is True
    assert all(not row.importable for row in preview.rows)


def test_kaspi_ocr_fallback_rejects_an_unreconciled_statement(monkeypatch):
    monkeypatch.setattr(kaspi_importer, "extract_pdf_pages", lambda content: ["ducuhpcyhuh"])
    monkeypatch.setattr(
        kaspi_importer,
        "extract_pdf_pages_ocr",
        lambda content: _kaspi_ocr_pages(closing="1 241,00"),
    )

    with pytest.raises(HTTPException, match="could not be reconciled"):
        KaspiPdfImporter().parse("kaspi.pdf", b"pdf")


def test_freedom_bank_pending_row_stays_visible_but_is_not_imported():
    pages = [
        "Фридом Банк Казахстан\nВыписка по карте",
        """Дата Сумма Валюта Операция Детали
17.09.2026
 -2.51 $ USD Сумма в
обработке WEIXIN Panduo platform Beijing CN
17.09.2026 +6,000.00 ₸ KZT Пополнение Перевод с карты на карту""",
    ]

    preview = FreedomBankPdfImporter().parse_pages("freedom.pdf", pages)

    assert len(preview.rows) == 2
    assert preview.rows[0].currency == "USD"
    assert preview.rows[0].importable is False
    assert preview.rows[1].amount == Decimal("6000.00")
    assert preview.rows[1].type.value == "income"


async def test_commit_preserves_merchant_currency_from_kaspi_fx_purchase(client: AsyncClient):
    kzt = (await client.get("/accounts")).json()[0]
    row = {
        "source_row": "page 2, operation 8",
        "date": "2026-09-17",
        "type": "expense",
        "amount": "2918.98",
        "account_currency": "KZT",
        "currency": "BYN",
        "transaction_amount": "19.58",
        "description": "Покупка",
        "details": "YANDEX.EDA",
    }

    response = await client.post(
        "/statement-imports/commit",
        json={"provider": "kaspi_gold_pdf", "accounts_by_currency": {"KZT": kzt["id"]}, "rows": [row]},
    )
    assert response.status_code == 200, response.text

    stored = (await client.get("/transactions")).json()["items"][0]
    assert money(stored["amount"]) == Decimal("2918.98")
    assert stored["currency"] == "BYN"
    assert money(stored["transaction_amount"]) == Decimal("19.58")
    assert money(stored["base_amount_kzt"]) == Decimal("2918.98")


async def test_tradernet_commit_is_atomic_and_idempotent(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(statement_import_service, "get_exchange_rate", _rate("500"))
    kzt = (await client.get("/accounts")).json()[0]
    usd = (
        await client.post("/accounts", json={"name": "Broker USD", "type": "investment", "currency": "USD"})
    ).json()
    preview = (await _preview(client)).json()
    payload = {
        "provider": "tradernet",
        "accounts_by_currency": {"KZT": kzt["id"], "USD": usd["id"]},
        "rows": preview["rows"],
    }

    first = await client.post("/statement-imports/commit", json=payload)
    assert first.status_code == 200, first.text
    assert first.json() == {"created": 2, "duplicates": 0, "ignored": 1}

    second = await client.post("/statement-imports/commit", json=payload)
    assert second.status_code == 200
    assert second.json() == {"created": 0, "duplicates": 2, "ignored": 1}


async def test_commit_stores_the_transaction_currency(client: AsyncClient, monkeypatch):
    """The regression this whole milestone exists for: an imported row must
    carry the currency fields the multicurrency ledger made mandatory."""
    monkeypatch.setattr(statement_import_service, "get_exchange_rate", _rate("500"))
    kzt = (await client.get("/accounts")).json()[0]
    usd = (
        await client.post("/accounts", json={"name": "Broker USD", "type": "investment", "currency": "USD"})
    ).json()
    preview = (await _preview(client)).json()
    payload = {
        "provider": "tradernet",
        "accounts_by_currency": {"KZT": kzt["id"], "USD": usd["id"]},
        "rows": preview["rows"],
    }

    assert (await client.post("/statement-imports/commit", json=payload)).status_code == 200

    usd_items = (await client.get("/transactions", params={"account_id": usd["id"]})).json()["items"]
    assert len(usd_items) == 1
    assert usd_items[0]["currency"] == "USD"
    assert money(usd_items[0]["transaction_amount"]) == Decimal("10.00")
    # The destination account is denominated in USD, so the account-side debit
    # and the transaction's own amount are the same figure.
    assert money(usd_items[0]["amount"]) == Decimal("10.00")
    assert money(usd_items[0]["base_amount_kzt"]) == Decimal("5000.00")


async def test_same_statement_into_a_second_account_is_not_treated_as_a_duplicate(
    client: AsyncClient, monkeypatch
):
    """Duplicate detection is (account, operation id), matching the database's
    own unique constraint — an operation id is not globally unique, so treating
    it as such would silently drop a legitimate second import."""
    monkeypatch.setattr(statement_import_service, "get_exchange_rate", _rate("500"))
    usd_first = (
        await client.post("/accounts", json={"name": "Broker A", "type": "investment", "currency": "USD"})
    ).json()
    usd_second = (
        await client.post("/accounts", json={"name": "Broker B", "type": "investment", "currency": "USD"})
    ).json()
    preview = (await _preview(client)).json()
    usd_rows = [row for row in preview["rows"] if row["currency"] == "USD"]

    first = await client.post(
        "/statement-imports/commit",
        json={"provider": "tradernet", "accounts_by_currency": {"USD": usd_first["id"]}, "rows": usd_rows},
    )
    second = await client.post(
        "/statement-imports/commit",
        json={"provider": "tradernet", "accounts_by_currency": {"USD": usd_second["id"]}, "rows": usd_rows},
    )

    assert first.json()["created"] == 1
    # The USD rows are the coupon plus the reservation, which is never posted.
    assert second.json() == {"created": 1, "duplicates": 0, "ignored": 1}


async def test_rows_without_an_operation_id_deduplicate_by_content(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(statement_import_service, "get_exchange_rate", _rate("500"))
    kzt = (await client.get("/accounts")).json()[0]
    content = _workbook([["", datetime(2026, 9, 18), "Карточный платеж", "Пополнение счёта картой", 5000, "KZT"]])
    preview = (await _preview(client, content)).json()
    assert preview["rows"][0]["external_id"] == ""
    payload = {"provider": "tradernet", "accounts_by_currency": {"KZT": kzt["id"]}, "rows": preview["rows"]}

    assert (await client.post("/statement-imports/commit", json=payload)).json()["created"] == 1
    assert (await client.post("/statement-imports/commit", json=payload)).json()["duplicates"] == 1

    stored = (await client.get("/transactions")).json()["items"][0]
    assert stored["external_id"].startswith("auto:")


async def test_edits_made_in_the_preview_are_what_gets_stored(
    client: AsyncClient, monkeypatch, categories
):
    """The parser's reading is a proposal: whatever the user corrects before
    pressing import is what must land in the ledger."""
    monkeypatch.setattr(statement_import_service, "get_exchange_rate", _rate("500"))
    kzt = (await client.get("/accounts")).json()[0]
    content = _workbook([["", datetime(2026, 9, 18), "Карточный платеж", "Пополнение", 5000, "KZT"]])
    rows = (await _preview(client, content)).json()["rows"]

    groceries = categories["Groceries"]["id"]
    rows[0] = {
        **rows[0],
        "description": "Продукты",
        "amount": "750.00",
        "transaction_amount": "750.00",
        "type": "expense",
        "category_id": groceries,
    }
    payload = {"provider": "tradernet", "accounts_by_currency": {"KZT": kzt["id"]}, "rows": rows}
    assert (await client.post("/statement-imports/commit", json=payload)).status_code == 200

    stored = (await client.get("/transactions")).json()["items"][0]
    assert stored["description"] == "Продукты"
    assert money(stored["amount"]) == Decimal("750.00")
    assert stored["type"] == "expense"
    assert stored["category_id"] == groceries
