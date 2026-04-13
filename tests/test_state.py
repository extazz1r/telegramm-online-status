from src.state import LoginPhase, LoginState


class TestLoginState:
    """Тесты управления состоянием авторизации."""

    def test_initial_state(self, login_state):
        assert login_state.is_idle
        assert not login_state.is_waiting_phone
        assert not login_state.is_waiting_code
        assert not login_state.is_waiting_password
        assert login_state.phone is None
        assert login_state.phone_code_hash is None

    def test_start_login(self, login_state):
        login_state.start_login()
        assert login_state.is_waiting_phone
        assert not login_state.is_idle
        assert login_state.phone is None
        assert login_state.phone_code_hash is None

    def test_phone_submitted(self, login_state):
        login_state.start_login()
        login_state.phone_submitted("+79001234567", "hash123")
        assert login_state.is_waiting_code
        assert login_state.phone == "+79001234567"
        assert login_state.phone_code_hash == "hash123"

    def test_password_required(self, login_state):
        login_state.start_login()
        login_state.phone_submitted("+79001234567", "hash123")
        login_state.password_required()
        assert login_state.is_waiting_password
        assert login_state.phone == "+79001234567"

    def test_reset_from_idle(self, login_state):
        login_state.reset()
        assert login_state.is_idle
        assert login_state.phone is None
        assert login_state.phone_code_hash is None

    def test_reset_from_waiting_code(self, login_state):
        login_state.start_login()
        login_state.phone_submitted("+79001234567", "hash123")
        login_state.reset()
        assert login_state.is_idle
        assert login_state.phone is None
        assert login_state.phone_code_hash is None

    def test_reset_from_waiting_password(self, login_state):
        login_state.start_login()
        login_state.phone_submitted("+79001234567", "hash123")
        login_state.password_required()
        login_state.reset()
        assert login_state.is_idle

    def test_start_login_clears_old_data(self, login_state):
        login_state.start_login()
        login_state.phone_submitted("+79001234567", "hash123")
        login_state.start_login()
        assert login_state.is_waiting_phone
        assert login_state.phone is None
        assert login_state.phone_code_hash is None

    def test_full_login_flow(self, login_state):
        """Проверка полного цикла авторизации."""
        assert login_state.phase == LoginPhase.IDLE
        login_state.start_login()
        assert login_state.phase == LoginPhase.WAITING_PHONE
        login_state.phone_submitted("+79001234567", "hash")
        assert login_state.phase == LoginPhase.WAITING_CODE
        login_state.password_required()
        assert login_state.phase == LoginPhase.WAITING_PASSWORD
        login_state.reset()
        assert login_state.phase == LoginPhase.IDLE

    def test_full_login_flow_without_2fa(self, login_state):
        """Проверка цикла авторизации без 2FA."""
        login_state.start_login()
        login_state.phone_submitted("+79001234567", "hash")
        assert login_state.is_waiting_code
        login_state.reset()
        assert login_state.is_idle
