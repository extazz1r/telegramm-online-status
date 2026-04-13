from unittest.mock import MagicMock

from src.utils import format_user_info, format_user_name


class TestFormatUserName:
    """Тесты форматирования имени пользователя."""

    def test_full_name(self, mock_user):
        assert format_user_name(mock_user) == "Иван Петров"

    def test_first_name_only(self):
        user = MagicMock()
        user.first_name = "Иван"
        user.last_name = None
        assert format_user_name(user) == "Иван"

    def test_empty_first_name_with_last(self):
        user = MagicMock()
        user.first_name = ""
        user.last_name = "Петров"
        assert format_user_name(user) == " Петров"

    def test_no_names(self):
        user = MagicMock()
        user.first_name = None
        user.last_name = None
        assert format_user_name(user) == ""


class TestFormatUserInfo:
    """Тесты форматирования полной информации о пользователе."""

    def test_with_username(self, mock_user):
        result = format_user_info(mock_user)
        assert "Иван Петров" in result
        assert "@ivanpetrov" in result
        assert "123456789" in result

    def test_without_username(self):
        user = MagicMock()
        user.first_name = "Иван"
        user.last_name = None
        user.username = None
        user.id = 999
        result = format_user_info(user)
        assert "Иван" in result
        assert "@" not in result
        assert "999" in result

    def test_info_has_id(self, mock_user):
        result = format_user_info(mock_user)
        assert f"ID: {mock_user.id}" in result
