import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    """Конфигурация приложения из переменных окружения."""

    def __init__(
        self,
        api_id: int | None = None,
        api_hash: str | None = None,
        bot_token: str | None = None,
        admin_id: int | None = None,
    ):
        self.api_id = api_id if api_id is not None else int(os.getenv("API_ID", 0))
        self.api_hash = api_hash if api_hash is not None else os.getenv("API_HASH", "")
        self.bot_token = bot_token if bot_token is not None else os.getenv("BOT_TOKEN", "")
        self.admin_id = admin_id if admin_id is not None else int(os.getenv("ADMIN_ID", 0))

    def validate(self) -> list[str]:
        """Возвращает список ошибок конфигурации."""
        errors = []
        if not self.api_id:
            errors.append("API_ID не задан")
        if not self.api_hash:
            errors.append("API_HASH не задан")
        if not self.bot_token:
            errors.append("BOT_TOKEN не задан")
        if not self.admin_id:
            errors.append("ADMIN_ID не задан")
        return errors
