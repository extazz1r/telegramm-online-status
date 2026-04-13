from unittest.mock import AsyncMock, MagicMock

import pytest

from src.state import LoginState


@pytest.fixture
def login_state():
    """Свежий экземпляр LoginState для каждого теста."""
    return LoginState()


@pytest.fixture
def mock_user():
    """Мок объекта пользователя Telegram."""
    user = MagicMock()
    user.first_name = "Иван"
    user.last_name = "Петров"
    user.username = "ivanpetrov"
    user.id = 123456789
    return user


@pytest.fixture
def mock_event():
    """Мок события Telegram."""
    event = AsyncMock()
    event.sender_id = 111
    event.text = ""
    event.respond = AsyncMock()
    return event


@pytest.fixture
def mock_user_client():
    """Мок Telethon-клиента для user-аккаунта."""
    client = AsyncMock()
    client.is_connected = MagicMock(return_value=False)
    return client
