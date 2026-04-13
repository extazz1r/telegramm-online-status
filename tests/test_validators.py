import pytest

from src.validators import parse_code, validate_phone


class TestValidatePhone:
    """Тесты валидации номера телефона."""

    def test_valid_phone(self):
        assert validate_phone("+79001234567") is None

    def test_valid_phone_with_spaces(self):
        assert validate_phone("  +79001234567  ") is None

    def test_valid_short_phone(self):
        assert validate_phone("+123456") is None

    def test_missing_plus(self):
        error = validate_phone("79001234567")
        assert error is not None
        assert "формат" in error.lower()

    def test_empty_string(self):
        error = validate_phone("")
        assert error is not None

    def test_plus_only(self):
        error = validate_phone("+")
        assert error is not None

    def test_letters_in_phone(self):
        error = validate_phone("+7900abc1234")
        assert error is not None

    def test_too_short(self):
        error = validate_phone("+123")
        assert error is not None
        assert "коротк" in error.lower()

    def test_spaces_inside_number(self):
        error = validate_phone("+7 900 123 4567")
        assert error is not None

    def test_dashes_in_number(self):
        error = validate_phone("+7-900-123-4567")
        assert error is not None


class TestParseCode:
    """Тесты парсинга кода подтверждения."""

    def test_plain_digits(self):
        assert parse_code("12345") == "12345"

    def test_digits_with_spaces(self):
        assert parse_code("1 2 3 4 5") == "12345"

    def test_digits_with_dashes(self):
        assert parse_code("1-2-3-4-5") == "12345"

    def test_mixed_separators(self):
        assert parse_code("1 2-3 4-5") == "12345"

    def test_four_digits(self):
        assert parse_code("1234") == "1234"

    def test_three_digits_too_short(self):
        assert parse_code("123") is None

    def test_empty_string(self):
        assert parse_code("") is None

    def test_no_digits(self):
        assert parse_code("abc") is None

    def test_mixed_text_and_digits(self):
        assert parse_code("код: 1 2 3 4 5") == "12345"

    def test_long_code(self):
        assert parse_code("123456") == "123456"
