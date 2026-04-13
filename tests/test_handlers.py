from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.handlers import _handle_code_input, _handle_password_input, _handle_phone_input
from src.state import LoginPhase, LoginState


ADMIN_ID = 111


class TestHandlePhoneInput:
    """Тесты обработки ввода номера телефона."""

    @pytest.mark.asyncio
    async def test_valid_phone_sends_code(self, mock_event, mock_user_client, login_state):
        mock_event.text = "+79001234567"
        code_result = MagicMock()
        code_result.phone_code_hash = "hash123"
        mock_user_client.send_code_request = AsyncMock(return_value=code_result)

        await _handle_phone_input(mock_event, mock_user_client, login_state)

        mock_user_client.send_code_request.assert_called_once_with("+79001234567")
        assert login_state.is_waiting_code
        assert login_state.phone == "+79001234567"
        assert login_state.phone_code_hash == "hash123"

    @pytest.mark.asyncio
    async def test_invalid_phone_rejected(self, mock_event, mock_user_client, login_state):
        login_state.start_login()
        mock_event.text = "invalid"

        await _handle_phone_input(mock_event, mock_user_client, login_state)

        mock_user_client.send_code_request.assert_not_called()
        assert login_state.is_waiting_phone  # state unchanged

    @pytest.mark.asyncio
    async def test_connects_if_not_connected(self, mock_event, mock_user_client, login_state):
        mock_event.text = "+79001234567"
        mock_user_client.is_connected = MagicMock(return_value=False)
        code_result = MagicMock()
        code_result.phone_code_hash = "hash"
        mock_user_client.send_code_request = AsyncMock(return_value=code_result)

        await _handle_phone_input(mock_event, mock_user_client, login_state)

        mock_user_client.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_connect_if_already_connected(self, mock_event, mock_user_client, login_state):
        mock_event.text = "+79001234567"
        mock_user_client.is_connected = MagicMock(return_value=True)
        code_result = MagicMock()
        code_result.phone_code_hash = "hash"
        mock_user_client.send_code_request = AsyncMock(return_value=code_result)

        await _handle_phone_input(mock_event, mock_user_client, login_state)

        mock_user_client.connect.assert_not_called()

    @pytest.mark.asyncio
    async def test_flood_wait_resets_state(self, mock_event, mock_user_client, login_state):
        from telethon.errors import FloodWaitError

        mock_event.text = "+79001234567"
        error = FloodWaitError(request=None, capture=0)
        error.seconds = 60
        mock_user_client.send_code_request = AsyncMock(side_effect=error)

        await _handle_phone_input(mock_event, mock_user_client, login_state)

        assert login_state.is_idle
        mock_event.respond.assert_called()
        last_msg = mock_event.respond.call_args_list[-1][0][0]
        assert "60" in last_msg

    @pytest.mark.asyncio
    async def test_generic_error_resets_state(self, mock_event, mock_user_client, login_state):
        mock_event.text = "+79001234567"
        mock_user_client.send_code_request = AsyncMock(side_effect=RuntimeError("test error"))

        await _handle_phone_input(mock_event, mock_user_client, login_state)

        assert login_state.is_idle


class TestHandleCodeInput:
    """Тесты обработки ввода кода подтверждения."""

    @pytest.mark.asyncio
    async def test_valid_code_signs_in(self, mock_event, mock_user_client, login_state, mock_user):
        login_state.start_login()
        login_state.phone_submitted("+79001234567", "hash123")
        mock_event.text = "1 2 3 4 5"
        mock_user_client.get_me = AsyncMock(return_value=mock_user)

        await _handle_code_input(mock_event, mock_user_client, login_state)

        mock_user_client.sign_in.assert_called_once_with(
            phone="+79001234567",
            code="12345",
            phone_code_hash="hash123",
        )
        assert login_state.is_idle

    @pytest.mark.asyncio
    async def test_invalid_code_rejected(self, mock_event, mock_user_client, login_state):
        login_state.start_login()
        login_state.phone_submitted("+79001234567", "hash123")
        mock_event.text = "12"

        await _handle_code_input(mock_event, mock_user_client, login_state)

        mock_user_client.sign_in.assert_not_called()
        assert login_state.is_waiting_code

    @pytest.mark.asyncio
    async def test_session_password_needed(self, mock_event, mock_user_client, login_state):
        from telethon.errors import SessionPasswordNeededError

        login_state.start_login()
        login_state.phone_submitted("+79001234567", "hash123")
        mock_event.text = "12345"
        mock_user_client.sign_in = AsyncMock(side_effect=SessionPasswordNeededError(request=None))

        await _handle_code_input(mock_event, mock_user_client, login_state)

        assert login_state.is_waiting_password

    @pytest.mark.asyncio
    async def test_invalid_code_error_keeps_state(self, mock_event, mock_user_client, login_state):
        from telethon.errors import PhoneCodeInvalidError

        login_state.start_login()
        login_state.phone_submitted("+79001234567", "hash123")
        mock_event.text = "12345"
        mock_user_client.sign_in = AsyncMock(side_effect=PhoneCodeInvalidError(request=None))

        await _handle_code_input(mock_event, mock_user_client, login_state)

        assert login_state.is_waiting_code  # can retry

    @pytest.mark.asyncio
    async def test_expired_code_resets_state(self, mock_event, mock_user_client, login_state):
        from telethon.errors import PhoneCodeExpiredError

        login_state.start_login()
        login_state.phone_submitted("+79001234567", "hash123")
        mock_event.text = "12345"
        mock_user_client.sign_in = AsyncMock(side_effect=PhoneCodeExpiredError(request=None))

        await _handle_code_input(mock_event, mock_user_client, login_state)

        assert login_state.is_idle

    @pytest.mark.asyncio
    async def test_successful_login_message(self, mock_event, mock_user_client, login_state, mock_user):
        login_state.start_login()
        login_state.phone_submitted("+79001234567", "hash123")
        mock_event.text = "12345"
        mock_user_client.get_me = AsyncMock(return_value=mock_user)

        await _handle_code_input(mock_event, mock_user_client, login_state)

        last_msg = mock_event.respond.call_args[0][0]
        assert "Иван Петров" in last_msg
        assert "успешно" in last_msg.lower()


class TestHandlePasswordInput:
    """Тесты обработки ввода пароля 2FA."""

    @pytest.mark.asyncio
    async def test_correct_password(self, mock_event, mock_user_client, login_state, mock_user):
        login_state.start_login()
        login_state.phone_submitted("+79001234567", "hash123")
        login_state.password_required()
        mock_event.text = "my_password"
        mock_user_client.get_me = AsyncMock(return_value=mock_user)

        await _handle_password_input(mock_event, mock_user_client, login_state)

        mock_user_client.sign_in.assert_called_once_with(password="my_password")
        assert login_state.is_idle

    @pytest.mark.asyncio
    async def test_wrong_password_keeps_state(self, mock_event, mock_user_client, login_state):
        from telethon.errors import PasswordHashInvalidError

        login_state.start_login()
        login_state.phone_submitted("+79001234567", "hash123")
        login_state.password_required()
        mock_event.text = "wrong"
        mock_user_client.sign_in = AsyncMock(side_effect=PasswordHashInvalidError(request=None))

        await _handle_password_input(mock_event, mock_user_client, login_state)

        assert login_state.is_waiting_password  # can retry

    @pytest.mark.asyncio
    async def test_flood_wait_resets_state(self, mock_event, mock_user_client, login_state):
        from telethon.errors import FloodWaitError

        login_state.start_login()
        login_state.phone_submitted("+79001234567", "hash123")
        login_state.password_required()
        mock_event.text = "pass"
        error = FloodWaitError(request=None, capture=0)
        error.seconds = 30
        mock_user_client.sign_in = AsyncMock(side_effect=error)

        await _handle_password_input(mock_event, mock_user_client, login_state)

        assert login_state.is_idle

    @pytest.mark.asyncio
    async def test_password_with_whitespace_stripped(self, mock_event, mock_user_client, login_state, mock_user):
        login_state.start_login()
        login_state.phone_submitted("+79001234567", "hash123")
        login_state.password_required()
        mock_event.text = "  my_password  "
        mock_user_client.get_me = AsyncMock(return_value=mock_user)

        await _handle_password_input(mock_event, mock_user_client, login_state)

        mock_user_client.sign_in.assert_called_once_with(password="my_password")

    @pytest.mark.asyncio
    async def test_generic_error_resets_state(self, mock_event, mock_user_client, login_state):
        login_state.start_login()
        login_state.phone_submitted("+79001234567", "hash123")
        login_state.password_required()
        mock_event.text = "pass"
        mock_user_client.sign_in = AsyncMock(side_effect=RuntimeError("oops"))

        await _handle_password_input(mock_event, mock_user_client, login_state)

        assert login_state.is_idle
