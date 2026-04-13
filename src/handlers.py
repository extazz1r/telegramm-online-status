import logging

from telethon import events
from telethon.errors import (
    FloodWaitError,
    PasswordHashInvalidError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
)

from .state import LoginState
from .utils import format_user_info, format_user_name
from .validators import parse_code, validate_phone

logger = logging.getLogger(__name__)


def register_handlers(bot, user_client, admin_id: int, state: LoginState):
    """Регистрирует все обработчики команд и сообщений на боте."""

    def is_admin(event) -> bool:
        return event.sender_id == admin_id

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
            await event.respond(format_user_info(me))
        else:
            await event.respond("Аккаунт не подключён. Используйте /login для входа.")

    @bot.on(events.NewMessage(pattern="/login"))
    async def cmd_login(event):
        if not is_admin(event):
            return
        if user_client.is_connected() and await user_client.is_user_authorized():
            await event.respond("Вы уже авторизованы! Используйте /logout для выхода.")
            return
        state.start_login()
        await event.respond(
            "Начинаем процесс входа.\n"
            "Отправьте номер телефона в международном формате (например: +79001234567):"
        )

    @bot.on(events.NewMessage(pattern="/cancel"))
    async def cmd_cancel(event):
        if not is_admin(event):
            return
        if state.is_idle:
            await event.respond("Нет активного процесса входа.")
            return
        state.reset()
        await event.respond("Процесс входа отменён.")

    @bot.on(events.NewMessage(pattern="/logout"))
    async def cmd_logout(event):
        if not is_admin(event):
            return
        if not user_client.is_connected() or not await user_client.is_user_authorized():
            await event.respond("Аккаунт не подключён.")
            return
        await user_client.log_out()
        state.reset()
        await event.respond("Вы успешно вышли из аккаунта.")

    @bot.on(events.NewMessage)
    async def handle_message(event):
        if not is_admin(event):
            return
        if event.text.startswith("/"):
            return

        if state.is_waiting_phone:
            await _handle_phone_input(event, user_client, state)
        elif state.is_waiting_code:
            await _handle_code_input(event, user_client, state)
        elif state.is_waiting_password:
            await _handle_password_input(event, user_client, state)


async def _handle_phone_input(event, user_client, state: LoginState):
    """Обработка ввода номера телефона."""
    phone = event.text.strip()
    error = validate_phone(phone)
    if error:
        await event.respond(error)
        return

    await event.respond("Отправляю код подтверждения...")

    try:
        if not user_client.is_connected():
            await user_client.connect()

        result = await user_client.send_code_request(phone)
        state.phone_submitted(phone, result.phone_code_hash)
        await event.respond(
            "Код отправлен! Введите код подтверждения из Telegram.\n"
            "Формат: цифры через пробел или дефис (например: 1 2 3 4 5 или 1-2-3-4-5),\n"
            "чтобы Telegram не перехватил сообщение."
        )
    except FloodWaitError as e:
        await event.respond(
            f"Слишком много попыток. Подождите {e.seconds} секунд и попробуйте снова."
        )
        state.reset()
    except Exception as e:
        logger.error(f"Ошибка при отправке кода: {e}")
        await event.respond(f"Ошибка при отправке кода: {e}")
        state.reset()


async def _handle_code_input(event, user_client, state: LoginState):
    """Обработка ввода кода подтверждения."""
    code = parse_code(event.text)
    if code is None:
        await event.respond("Введите корректный код (минимум 4 цифры).")
        return

    try:
        await user_client.sign_in(
            phone=state.phone,
            code=code,
            phone_code_hash=state.phone_code_hash,
        )
        state.reset()
        me = await user_client.get_me()
        name = format_user_name(me)
        await event.respond(f"Вход выполнен успешно! Добро пожаловать, {name}!")

    except SessionPasswordNeededError:
        state.password_required()
        await event.respond(
            "У вас включена двухфакторная аутентификация.\n"
            "Введите облачный пароль:"
        )
    except PhoneCodeInvalidError:
        await event.respond("Неверный код. Попробуйте ещё раз:")
    except PhoneCodeExpiredError:
        await event.respond("Код истёк. Используйте /login чтобы запросить новый.")
        state.reset()
    except FloodWaitError as e:
        await event.respond(
            f"Слишком много попыток. Подождите {e.seconds} секунд."
        )
        state.reset()
    except Exception as e:
        logger.error(f"Ошибка при вводе кода: {e}")
        await event.respond(f"Ошибка: {e}")
        state.reset()


async def _handle_password_input(event, user_client, state: LoginState):
    """Обработка ввода облачного пароля (2FA)."""
    password = event.text.strip()

    try:
        await user_client.sign_in(password=password)
        state.reset()
        me = await user_client.get_me()
        name = format_user_name(me)
        await event.respond(f"Вход выполнен успешно! Добро пожаловать, {name}!")

    except PasswordHashInvalidError:
        await event.respond("Неверный пароль. Попробуйте ещё раз:")
    except FloodWaitError as e:
        await event.respond(
            f"Слишком много попыток. Подождите {e.seconds} секунд."
        )
        state.reset()
    except Exception as e:
        logger.error(f"Ошибка при вводе пароля: {e}")
        await event.respond(f"Ошибка: {e}")
        state.reset()
