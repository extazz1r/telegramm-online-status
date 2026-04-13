import os
import asyncio
import logging

from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PasswordHashInvalidError,
    PhoneCodeExpiredError,
    FloodWaitError,
)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

# Бот-клиент (для интерфейса с пользователем)
bot = TelegramClient("bot_session", API_ID, API_HASH)

# Userbot-клиент (для входа в аккаунт пользователя)
user_client = TelegramClient("user_session", API_ID, API_HASH)

# Состояния авторизации
LOGIN_IDLE = 0
WAITING_PHONE = 1
WAITING_CODE = 2
WAITING_PASSWORD = 3

login_state = LOGIN_IDLE
login_phone = None
phone_code_hash = None


def is_admin(event):
    """Проверяет, что сообщение от администратора."""
    return event.sender_id == ADMIN_ID


@bot.on(events.NewMessage(pattern="/start"))
async def cmd_start(event):
    if not is_admin(event):
        return
    await event.respond(
        "Привет! Я бот для входа в Telegram-аккаунт.\n\n"
        "Команды:\n"
        "/login — начать вход в аккаунт\n"
        "/status — проверить статус подключения\n"
        "/logout — выйти из аккаунта\n"
        "/cancel — отменить процесс входа"
    )


@bot.on(events.NewMessage(pattern="/status"))
async def cmd_status(event):
    if not is_admin(event):
        return
    if user_client.is_connected() and await user_client.is_user_authorized():
        me = await user_client.get_me()
        name = me.first_name or ""
        if me.last_name:
            name += f" {me.last_name}"
        username = f" (@{me.username})" if me.username else ""
        await event.respond(
            f"Аккаунт подключён: {name}{username}\n"
            f"ID: {me.id}"
        )
    else:
        await event.respond("Аккаунт не подключён. Используйте /login для входа.")


@bot.on(events.NewMessage(pattern="/login"))
async def cmd_login(event):
    global login_state
    if not is_admin(event):
        return

    if user_client.is_connected() and await user_client.is_user_authorized():
        await event.respond("Вы уже авторизованы! Используйте /logout для выхода.")
        return

    login_state = WAITING_PHONE
    await event.respond(
        "Начинаем процесс входа.\n"
        "Отправьте номер телефона в международном формате (например: +79001234567):"
    )


@bot.on(events.NewMessage(pattern="/cancel"))
async def cmd_cancel(event):
    global login_state, login_phone, phone_code_hash
    if not is_admin(event):
        return

    if login_state == LOGIN_IDLE:
        await event.respond("Нет активного процесса входа.")
        return

    login_state = LOGIN_IDLE
    login_phone = None
    phone_code_hash = None
    await event.respond("Процесс входа отменён.")


@bot.on(events.NewMessage(pattern="/logout"))
async def cmd_logout(event):
    global login_state
    if not is_admin(event):
        return

    if not user_client.is_connected() or not await user_client.is_user_authorized():
        await event.respond("Аккаунт не подключён.")
        return

    await user_client.log_out()
    login_state = LOGIN_IDLE
    await event.respond("Вы успешно вышли из аккаунта.")


@bot.on(events.NewMessage)
async def handle_message(event):
    global login_state, login_phone, phone_code_hash

    if not is_admin(event):
        return

    # Игнорируем команды — они обрабатываются отдельно
    if event.text.startswith("/"):
        return

    # --- Ввод номера телефона ---
    if login_state == WAITING_PHONE:
        phone = event.text.strip()
        if not phone.startswith("+") or not phone[1:].isdigit():
            await event.respond(
                "Неверный формат номера. Используйте международный формат, например: +79001234567"
            )
            return

        login_phone = phone
        await event.respond("Отправляю код подтверждения...")

        try:
            if not user_client.is_connected():
                await user_client.connect()

            result = await user_client.send_code_request(phone)
            phone_code_hash = result.phone_code_hash
            login_state = WAITING_CODE
            await event.respond(
                "Код отправлен! Введите код подтверждения из Telegram.\n"
                "Формат: цифры через пробел или дефис (например: 1 2 3 4 5 или 1-2-3-4-5),\n"
                "чтобы Telegram не перехватил сообщение."
            )
        except FloodWaitError as e:
            await event.respond(
                f"Слишком много попыток. Подождите {e.seconds} секунд и попробуйте снова."
            )
            login_state = LOGIN_IDLE
        except Exception as e:
            logger.error(f"Ошибка при отправке кода: {e}")
            await event.respond(f"Ошибка при отправке кода: {e}")
            login_state = LOGIN_IDLE
        return

    # --- Ввод кода подтверждения ---
    if login_state == WAITING_CODE:
        # Убираем пробелы, дефисы и другие разделители — оставляем только цифры
        code = "".join(c for c in event.text if c.isdigit())

        if not code or len(code) < 4:
            await event.respond("Введите корректный код (минимум 4 цифры).")
            return

        try:
            await user_client.sign_in(
                phone=login_phone,
                code=code,
                phone_code_hash=phone_code_hash,
            )
            login_state = LOGIN_IDLE
            me = await user_client.get_me()
            name = me.first_name or ""
            if me.last_name:
                name += f" {me.last_name}"
            await event.respond(f"Вход выполнен успешно! Добро пожаловать, {name}!")

        except SessionPasswordNeededError:
            login_state = WAITING_PASSWORD
            await event.respond(
                "У вас включена двухфакторная аутентификация.\n"
                "Введите облачный пароль:"
            )
        except PhoneCodeInvalidError:
            await event.respond("Неверный код. Попробуйте ещё раз:")
        except PhoneCodeExpiredError:
            await event.respond("Код истёк. Используйте /login чтобы запросить новый.")
            login_state = LOGIN_IDLE
        except FloodWaitError as e:
            await event.respond(
                f"Слишком много попыток. Подождите {e.seconds} секунд."
            )
            login_state = LOGIN_IDLE
        except Exception as e:
            logger.error(f"Ошибка при вводе кода: {e}")
            await event.respond(f"Ошибка: {e}")
            login_state = LOGIN_IDLE
        return

    # --- Ввод облачного пароля ---
    if login_state == WAITING_PASSWORD:
        password = event.text.strip()

        try:
            await user_client.sign_in(password=password)
            login_state = LOGIN_IDLE
            me = await user_client.get_me()
            name = me.first_name or ""
            if me.last_name:
                name += f" {me.last_name}"
            await event.respond(f"Вход выполнен успешно! Добро пожаловать, {name}!")

        except PasswordHashInvalidError:
            await event.respond("Неверный пароль. Попробуйте ещё раз:")
        except FloodWaitError as e:
            await event.respond(
                f"Слишком много попыток. Подождите {e.seconds} секунд."
            )
            login_state = LOGIN_IDLE
        except Exception as e:
            logger.error(f"Ошибка при вводе пароля: {e}")
            await event.respond(f"Ошибка: {e}")
            login_state = LOGIN_IDLE
        return


async def main():
    logger.info("Запуск бота...")

    await bot.start(bot_token=BOT_TOKEN)
    logger.info("Бот запущен.")

    # Пробуем подключить user-клиент, если сессия уже есть
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


if __name__ == "__main__":
    asyncio.run(main())
