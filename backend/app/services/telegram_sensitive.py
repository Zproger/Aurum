"""Detect sensitive data in incoming Telegram messages before anything is stored."""
from __future__ import annotations

import re
from collections.abc import Iterable

# Bot API 10.4 marks bank card numbers with this entity type.
BANK_CARD_ENTITY = "bank_card_number"
# A run of digit groups split by single spaces or dashes, e.g. "500 4111 1111".
DIGIT_RUN_RE = re.compile(r"\d+(?:[ -]\d+)*")
CARD_MIN_DIGITS = 13
CARD_MAX_DIGITS = 19


def luhn_valid(digits: str) -> bool:
    """Luhn checksum used by every payment card number."""
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def has_bank_card_number(text: str, entities: Iterable[dict] | None = None) -> bool:
    """True when the message looks like it carries a payment card number.

    Telegram's own entity is trusted first. The Luhn fallback covers clients or
    messages where the entity is missing; plain amounts and phone numbers are
    too short to match.
    """
    for entity in entities or ():
        if isinstance(entity, dict) and entity.get("type") == BANK_CARD_ENTITY:
            return True
    for match in DIGIT_RUN_RE.finditer(text or ""):
        if _run_has_card(re.split(r"[ -]", match.group(0))):
            return True
    return False


def _run_has_card(groups: list[str]) -> bool:
    """Try every sequence of whole adjacent groups, so "-500 4111 1111 1111 1111"
    still finds the card after the amount."""
    for start in range(len(groups)):
        digits = ""
        for group in groups[start:]:
            digits += group
            if len(digits) > CARD_MAX_DIGITS:
                break
            if len(digits) >= CARD_MIN_DIGITS and luhn_valid(digits):
                return True
    return False
