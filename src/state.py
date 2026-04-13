from enum import IntEnum


class LoginPhase(IntEnum):
    """Фазы процесса авторизации."""

    IDLE = 0
    WAITING_PHONE = 1
    WAITING_CODE = 2
    WAITING_PASSWORD = 3


class LoginState:
    """Управление состоянием процесса авторизации."""

    def __init__(self):
        self.phase: LoginPhase = LoginPhase.IDLE
        self.phone: str | None = None
        self.phone_code_hash: str | None = None

    @property
    def is_idle(self) -> bool:
        return self.phase == LoginPhase.IDLE

    @property
    def is_waiting_phone(self) -> bool:
        return self.phase == LoginPhase.WAITING_PHONE

    @property
    def is_waiting_code(self) -> bool:
        return self.phase == LoginPhase.WAITING_CODE

    @property
    def is_waiting_password(self) -> bool:
        return self.phase == LoginPhase.WAITING_PASSWORD

    def start_login(self):
        """Начать процесс авторизации — ожидание номера телефона."""
        self.phase = LoginPhase.WAITING_PHONE
        self.phone = None
        self.phone_code_hash = None

    def phone_submitted(self, phone: str, phone_code_hash: str):
        """Номер телефона принят, код отправлен."""
        self.phone = phone
        self.phone_code_hash = phone_code_hash
        self.phase = LoginPhase.WAITING_CODE

    def password_required(self):
        """Требуется ввод облачного пароля (2FA)."""
        self.phase = LoginPhase.WAITING_PASSWORD

    def reset(self):
        """Сбросить состояние авторизации."""
        self.phase = LoginPhase.IDLE
        self.phone = None
        self.phone_code_hash = None
