"""Card numbers must be recognised before a Telegram message reaches a draft,
while ordinary quick entries, phones and link codes pass through untouched."""
import pytest

from app.services.telegram_sensitive import has_bank_card_number, luhn_valid

# A published test Visa number that passes the Luhn check.
TEST_CARD = "4111111111111111"


def test_telegram_entity_is_trusted_even_without_digits_in_text():
    entities = [{"type": "bold", "offset": 0, "length": 3}, {"type": "bank_card_number", "offset": 4, "length": 19}]

    assert has_bank_card_number("abc whatever", entities) is True


def test_non_dict_entities_are_ignored():
    assert has_bank_card_number("-2500 кофе", ["bank_card_number", None, 42]) is False


@pytest.mark.parametrize(
    "text",
    [
        "4111 1111 1111 1111",
        "4111-1111-1111-1111",
        TEST_CARD,
        "-500 4111 1111 1111 1111",
        "оплата картой 4111 1111 1111 1111 спасибо",
        # 13 and 19 digit boundaries that pass Luhn.
        "4222222222222",
        "4111 1111 1111 1111 004",
    ],
)
def test_luhn_fallback_finds_card_numbers(text):
    assert has_bank_card_number(text, None) is True


@pytest.mark.parametrize(
    "text",
    [
        "-2500 кофе",
        "+500000 зарплата",
        "+7 701 234 56 78",
        "/link AB12CD34",
        "1234 5678 9012 3456",
        "",
        "   ",
        # 12 digits pass Luhn but are too short for a card.
        "411111111111",
        # Two spaces or a dot break the run of adjacent groups.
        "4111  1111  1111  1111",
        "4111.1111.1111.1111",
    ],
)
def test_ordinary_messages_are_not_flagged(text):
    assert has_bank_card_number(text, None) is False


def test_bad_checksum_is_really_a_bad_checksum():
    # Guards the negative case above from silently becoming a positive one.
    assert luhn_valid("1234567890123456") is False
    assert luhn_valid(TEST_CARD) is True


def test_none_text_and_none_entities_are_safe():
    assert has_bank_card_number(None, None) is False  # type: ignore[arg-type]
    assert has_bank_card_number("-2500 кофе") is False
