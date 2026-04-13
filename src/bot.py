import asyncio
import logging

from telethon import TelegramClient

from .config import Config
from .handlers import register_handlers
from .state import LoginState

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def create_clients(config: Config) -> tuple[TelegramClient, TelegramClient]:
    """Создаёт бот-клиент и user-клиент."""
    bot = TelegramClient("bot_session", config.api_id, config.api_hash)
    user_client = TelegramClient("user_session", config.api_id, config.api_hash)
    return bot, user_client


async def main():
    config = Config()
    errors = config.validate()
    if errors:
        for err in errors:
            logger.error(err)
        return

    bot, user_client = create_clients(config)
    state = LoginState()

    register_handlers(bot, user_client, config.admin_id, state)

    logger.info("Запуск бота...")
    await bot.start(bot_token=config.bot_token)
    logger.info("Бот запущен.")

    try:
        await user_client.connect()
        if await user_client.is_user_authorized():
            me = await user_client.get_me()
            logger.info(f"User-клиент подключён: {me.first_name} (ID: {me.id})")
        else:
            logger.info("User-клиент не авторизован. Используйте /login в боте.")
    except Exception as e:
        logger.warning(f"Не удалось подключить user-клиент: {e}")

    logger.info("Бот готов к работе. Нажмите Ctrl+C для остановки.")
    await bot.run_until_disconnected()


def run():
    asyncio.run(main())
