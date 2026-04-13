import os
import asyncio
import logging
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.tl.types import (
    UserStatusOnline,
    UserStatusOffline,
    UserStatusRecently,
    UserStatusLastWeek,
    UserStatusLastMonth,
)
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

# Мониторинг статуса
watched_username = None
last_known_status = None
CHECK_INTERVAL = 5 * 60  # 5 минут в секундах


def is_admin(event):
    """Проверяет, что сообщение от администратора."""
    return event.sender_id == ADMIN_ID


def format_status(status):
    """Форматирует статус пользователя в читаемую строку."""
    if isinstance(status, UserStatusOnline):
        return "В сети"
    elif isinstance(status, UserStatusOffline):
        was_online = status.was_online
        if was_online:
            # Конвертируем в московское время (UTC+3)
            local_time = was_online.strftime("%d.%m.%Y %H:%M:%S UTC")
            return f"Не в сети (был(а) {local_time})"
        return "Не в сети"
    elif isinstance(status, UserStatusRecently):
        return "Был(а) недавно"
    elif isinstance(status, UserStatusLastWeek):
        return "Был(а) на этой неделе"
    elif isinstance(status, UserStatusLastMonth):
        return "Был(а) в этом месяце"
    elif status is None:
        return "Статус скрыт"
    return "Неизвестный статус"


def status_changed(old_status, new_status):
    """Проверяет, изменился ли статус."""
    if type(old_status) != type(new_status):
        return True
    # Для UserStatusOffline сравниваем время was_online
    if isinstance(old_status, UserStatusOffline) and isinstance(new_status, UserStatusOffline):
        return old_status.was_online != new_status.was_online
    return False


async def monitor_loop():
    """Фоновая задача: проверяет статус каждые CHECK_INTERVAL секунд."""
    global last_known_status, watched_username

    while True:
        await asyncio.sleep(CHECK_INTERVAL)

        if not watched_username:
            continue

        if not user_client.is_connected() or not await user_client.is_user_authorized():
            logger.warning("User-клиент не авторизован, мониторинг приостановлен.")
            continue

        try:
            entity = await user_client.get_entity(watched_username)
            new_status = entity.status
            new_text = format_status(new_status)

            if last_known_status is None or status_changed(last_known_status, new_status):
                old_text = format_status(last_known_status) if last_known_status is not None else "—"
                await bot.send_message(
                    ADMIN_ID,
                    f"👤 @{watched_username}\n"
                    f"Было: {old_text}\n"
                    f"Стало: {new_text}",
                )
                last_known_status = new_status
            else:
                logger.info(f"Статус @{watched_username} не изменился: {new_text}")

        except Exception as e:
            logger.error(f"Ошибка при проверке статуса @{watched_username}: {e}")
            await bot.send_message(
                ADMIN_ID,
                f"Ошибка при проверке статуса @{watched_username}: {e}",
            )


@bot.on(events.NewMessage(pattern="/start"))
async def cmd_start(event):
    if not is_admin(event):
        return
    await event.respond(
        "Привет! Я бот для входа в Telegram-аккаунт и отслеживания онлайн-статуса.\n\n"
        "Команды:\n"
        "/login — начать вход в аккаунт\n"
        "/status — проверить статус подключения\n"
        "/logout — выйти из аккаунта\n"
        "/cancel — отменить процесс входа\n"
        "/watch — отслеживать статус пользователя (отправьте юзернейм после команды)\n"
        "/unwatch — прекратить отслеживание"
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


@bot.on(events.NewMessage(pattern=r"/watch"))
async def cmd_watch(event):
    global watched_username, last_known_status
    if not is_admin(event):
        return

    if not user_client.is_connected() or not await user_client.is_user_authorized():
        await event.respond("Сначала войдите в аккаунт через /login")
        return

    # Извлекаем юзернейм из команды: /watch username или /watch @username
    parts = event.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await event.respond(
            "Укажите юзернейм после команды.\n"
            "Пример: /watch username или /watch @username"
        )
        return

    username = parts[1].strip().lstrip("@")

    # Проверяем, что пользователь существует и доступен
    try:
        entity = await user_client.get_entity(username)
    except Exception as e:
        await event.respond(
            f"Не удалось найти пользователя @{username}.\n"
            f"Убедитесь, что юзернейм указан верно и у вас есть чат с этим пользователем.\n"
            f"Ошибка: {e}"
        )
        return

    watched_username = username
    last_known_status = entity.status
    current_status = format_status(entity.status)

    name = entity.first_name or ""
    if entity.last_name:
        name += f" {entity.last_name}"

    await event.respond(
        f"Начинаю отслеживание @{username} ({name}).\n"
        f"Текущий статус: {current_status}\n"
        f"Проверка каждые 5 минут. Вы получите уведомление при изменении статуса.\n"
        f"Для остановки: /unwatch"
    )
    logger.info(f"Начато отслеживание @{username}")


@bot.on(events.NewMessage(pattern="/unwatch"))
async def cmd_unwatch(event):
    global watched_username, last_known_status
    if not is_admin(event):
        return

    if not watched_username:
        await event.respond("Сейчас никто не отслеживается.")
        return

    old_username = watched_username
    watched_username = None
    last_known_status = None
    await event.respond(f"Отслеживание @{old_username} остановлено.")
    logger.info(f"Остановлено отслеживание @{old_username}")


@bot.on(events.NewMessage(pattern="/logout"))
async def cmd_logout(event):
    global login_state, watched_username, last_known_status
    if not is_admin(event):
        return

    if not user_client.is_connected() or not await user_client.is_user_authorized():
        await event.respond("Аккаунт не подключён.")
        return

    # Останавливаем мониторинг при выходе
    if watched_username:
        logger.info(f"Остановлено отслеживание @{watched_username} (logout)")
        watched_username = None
        last_known_status = None

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

    # Запускаем фоновую задачу мониторинга статуса
    asyncio.create_task(monitor_loop())
    logger.info("Фоновый мониторинг запущен (интервал: 5 мин).")

    logger.info("Бот готов к работе. Нажмите Ctrl+C для остановки.")
    await bot.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
