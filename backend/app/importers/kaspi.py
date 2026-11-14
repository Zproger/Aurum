"""Kaspi Gold text-PDF statements (Russian 2026 layout)."""
import re
from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException

from app.importers.base import StatementImporter
from app.importers.pdf_text import extract_pdf_pages, extract_pdf_pages_ocr
from app.models.enums import TransactionPurpose, TransactionType
from app.schemas.statement_import import StatementPreview, StatementRow

_ROW = re.compile(r"^(\d{2}\.\d{2}\.\d{2})\s+([+-])\s*([\d ]+,\d{2})\s*[₸TТ]\s+(.+)$")
_ORIGINAL = re.compile(r"^\(\s*-?\s*([\d ]+,\d{2})\s+([A-Z]{3})\s*\)$")
_BALANCE = re.compile(r"([+-])\s*([\d ]+,\d{2})\s*[₸TТ]")
_AVAILABLE_DATE = re.compile(r"Доступно на (\d{2}\.\d{2}\.\d{2})", re.IGNORECASE)
_INCOMING = re.compile(r"^Поступление\s+[сc][оo]\b", re.IGNORECASE)
_OCR_PENDING_INCOMING = re.compile(r"^S[cс]\s+", re.IGNORECASE)
_OCR_WARNING = "Local OCR was used; review every row before importing"
# Kaspi marks a card purchase that is still awaiting the payment system with
# "- Сумма заблокирована…" under the row. The money has already left the
# available balance (the statement reconciles with it), so it is imported as
# spent; the user can still untick it in the preview.
BLOCKED_WARNING = "Blocked amount awaiting confirmation; imported as spent"
_OPERATIONS = sorted(
    ("Поступление со своего счета", "Перевод на свой счет", "Пополнение", "Покупка", "Перевод", "Снятие", "Разное"),
    key=len,
    reverse=True,
)


def _money(value: str) -> Decimal:
    return Decimal(value.replace(" ", "").replace(",", "."))


def _signed_balance(line: str) -> Decimal | None:
    match = _BALANCE.search(line)
    if not match:
        return None
    value = _money(match.group(2))
    return value if match.group(1) == "+" else -value


class KaspiPdfImporter(StatementImporter):
    id = "kaspi_gold_pdf"
    label = "Kaspi Gold PDF"
    extensions = (".pdf",)

    def parse(self, file_name: str, content: bytes) -> StatementPreview:
        used_ocr = False
        try:
            pages = extract_pdf_pages(content)
        except HTTPException as exc:
            if "local OCR is required" not in str(exc.detail):
                raise
            pages = extract_pdf_pages_ocr(content)
            used_ocr = True

        try:
            preview = self.parse_pages(file_name, pages)
        except HTTPException as exc:
            text = "\n".join(pages)
            readable_cyrillic = sum("А" <= char <= "я" or char in "Ёё" for char in text) >= 20
            if used_ocr or exc.detail != "Not a supported Kaspi Gold statement" or readable_cyrillic:
                raise
            preview = self.parse_pages(file_name, extract_pdf_pages_ocr(content))
            used_ocr = True

        if used_ocr:
            if "Balance check passed: opening balance plus operations equals closing balance" not in preview.warnings:
                raise HTTPException(422, "The OCR statement could not be reconciled; review the source PDF")
            preview.warnings.insert(0, _OCR_WARNING)
            preview.requires_row_confirmation = True
            for row in preview.rows:
                row.importable = False
                row.warning = row.warning or "OCR row requires explicit confirmation"
        return preview

    def parse_pages(self, file_name: str, pages: list[str]) -> StatementPreview:
        text = "\n".join(pages)
        if "Kaspi Bank" not in text or "Kaspi Gold" not in text or "ВЫПИСКА" not in text.upper():
            raise HTTPException(422, "Not a supported Kaspi Gold statement")

        physical = [(page_no, line.strip()) for page_no, page in enumerate(pages, 1) for line in page.splitlines()]
        chunks: list[tuple[int, str, list[str]]] = []
        current: tuple[int, str, list[str]] | None = None
        for page_no, line in physical:
            match = _ROW.match(line)
            if match:
                if current:
                    chunks.append(current)
                current = (page_no, line, [])
            elif current:
                if line.startswith("- Сумма заблокирована"):
                    current[2].append(line)
                elif not line or line.startswith(
                    (
                        "ИТОГО",
                        "Дата Сумма",
                        "Kaspi Bank",
                        "АО ",
                        "AO ",
                        "Доступно на",
                        "Остаток на конец",
                        "Раздел «",
                    )
                ):
                    chunks.append(current)
                    current = None
                else:
                    current[2].append(line)
        if current:
            chunks.append(current)
        if not chunks:
            raise HTTPException(422, "Kaspi operation table was not found")

        rows: list[StatementRow] = []
        signed_total = Decimal("0")
        for index, (page_no, first, continuation) in enumerate(chunks, 1):
            match = _ROW.match(first)
            assert match is not None
            raw_date, sign, raw_amount, rest = match.groups()
            amount = _money(raw_amount)
            signed_total += amount if sign == "+" else -amount
            pending = any("Сумма заблокирована" in line for line in continuation)
            original_amount: Decimal | None = None
            original_currency = "KZT"
            words = [rest]
            for line in continuation:
                original = _ORIGINAL.match(line)
                if original:
                    original_amount = _money(original.group(1))
                    original_currency = original.group(2)
                elif not line.startswith("- Сумма заблокирована"):
                    words.append(line)
            joined = " ".join(words)
            joined = re.sub(r"^Pa3Hoe\b", "Разное", joined, flags=re.IGNORECASE)
            if joined.startswith("Перевод на свой"):
                operation = "Перевод на свой счет"
                details = joined[len("Перевод на свой"):].strip()
                details = details.removesuffix(" счет").strip()
            elif incoming := _INCOMING.match(joined):
                operation = "Поступление со своего счета"
                details = joined[incoming.end():].strip()
                if marker := _OCR_PENDING_INCOMING.match(details):
                    pending = True
                    details = details[marker.end():].strip()
                details = details.removesuffix(" своего счета").strip()
            else:
                operation = next((name for name in _OPERATIONS if joined.startswith(name)), joined)
                details = joined[len(operation):].strip()
            if details.startswith("©"):
                pending = True
                details = details.removeprefix("©").strip()
            details = details or None
            internal = operation in {"Перевод на свой счет", "Поступление со своего счета"}
            warning = None
            if internal:
                warning = "Own-account transfer needs the other account and is not imported as income/expense"
            elif pending:
                warning = BLOCKED_WARNING
            purpose = TransactionPurpose.FEE if operation == "Разное" and details and "комис" in details.casefold() else TransactionPurpose.ORDINARY
            rows.append(
                StatementRow(
                    source_row=f"page {page_no}, operation {index}",
                    date=datetime.strptime(raw_date, "%d.%m.%y").date(),
                    type=TransactionType.INCOME if sign == "+" else TransactionType.EXPENSE,
                    amount=amount,
                    account_currency="KZT",
                    currency=original_currency,
                    transaction_amount=original_amount or amount,
                    description=operation,
                    details=details,
                    purpose=purpose,
                    importable=not internal,
                    warning=warning,
                )
            )

        warnings: list[str] = []
        balances: dict[datetime, Decimal] = {}
        for line in text.splitlines():
            available = _AVAILABLE_DATE.search(line)
            if available:
                balance = _signed_balance(line)
                if balance is not None:
                    balances[datetime.strptime(available.group(1), "%d.%m.%y")] = balance
        ordered_balances = [balances[key] for key in sorted(balances)]
        opening = ordered_balances[0] if ordered_balances else None
        closing = ordered_balances[-1] if len(ordered_balances) > 1 else None
        if opening is not None and closing is not None and opening + signed_total != closing:
            warnings.append(
                f"Balance check failed: {opening} + {signed_total} != {closing} KZT; review all PDF rows"
            )
        elif opening is not None and closing is not None:
            warnings.append("Balance check passed: opening balance plus operations equals closing balance")
        else:
            warnings.append("Opening/closing balance was not found; reconciliation was not possible")
        return StatementPreview(
            provider=self.id, provider_label=self.label, file_name=file_name, rows=rows, warnings=warnings
        )
