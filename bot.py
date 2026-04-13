import os
import asyncio
import logging
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
from telethon import TelegramClient, events, Button
from telethon.tl.types import (
    UserStatusOnline,
    UserStatusOffline,
    UserStatusRecently,
    UserStatusLastWeek,
    UserStatusLastMonth,
)
from telethon.tl.functions.users import GetUsersRequest
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

MSK = timezone(timedelta(hours=3))

# Состояния
LOGIN_IDLE = 0
WAITING_PHONE = 1
WAITING_CODE = 2
WAITING_PASSWORD = 3
WAITING_USERNAME = 4

login_state = LOGIN_IDLE
login_phone = None
phone_code_hash = None

# Мониторинг
watched_username = None
watched_input_peer = None
last_known_status = None
CHECK_INTERVAL = 5

# Настройки уведомлений
notify_settings = {
    "online": True,     # 🟢 Зашёл в сеть
    "offline": True,    # 🔴 Вышел из сети
    "recently": False,  # 🟡 Был(а) недавно
    "weekly": False,    # 🟠 Был(а) на этой неделе
    "monthly": False,   # 🟠 Был(а) в этом месяце
}

# Клиенты создаются в main()
bot = None
user_client = None


def is_admin(event):
    return event.sender_id == ADMIN_ID


def format_status(status):
    if isinstance(status, UserStatusOnline):
        return "🟢 В сети"
    elif isinstance(status, UserStatusOffline):
        was_online = status.was_online
        if was_online:
            msk_time = was_online.replace(tzinfo=timezone.utc).astimezone(MSK)
            local_time = msk_time.strftime("%d.%m.%Y %H:%M:%S")
            return f"🔴 Не в сети (был(а) {local_time} МСК)"
        return "🔴 Не в сети"
    elif isinstance(status, UserStatusRecently):
        return "🟡 Был(а) недавно"
    elif isinstance(status, UserStatusLastWeek):
        return "🟠 Был(а) на этой неделе"
    elif isinstance(status, UserStatusLastMonth):
        return "🟠 Был(а) в этом месяце"
    elif status is None:
        return "⚪ Статус скрыт"
    return "❓ Неизвестный статус"


def status_changed(old_status, new_status):
    if type(old_status) != type(new_status):
        return True
    if isinstance(old_status, UserStatusOffline) and isinstance(new_status, UserStatusOffline):
        return old_status.was_online != new_status.was_online
    return False


async def send_main_menu(event):
    is_authorized = user_client and user_client.is_connected() and await user_client.is_user_authorized()

    if is_authorized:
        me = await user_client.get_me()
        name = me.first_name or ""
        if me.last_name:
            name += f" {me.last_name}"
        uname = f" (@{me.username})" if me.username else ""

        watch_text = f"👁 Отслеживается: @{watched_username}" if watched_username else ""

        buttons = []
        if watched_username:
            buttons.append([Button.inline("🔍 Проверить статус сейчас", b"check_now")])
            buttons.append([Button.inline("🛑 Остановить отслеживание", b"unwatch")])
        else:
            buttons.append([Button.inline("👁 Отслеживать пользователя", b"watch")])
        buttons.append([Button.inline("⚙️ Настройки уведомлений", b"settings")])
        buttons.append([Button.inline("ℹ️ Статус аккаунта", b"status")])
        buttons.append([Button.inline("🚪 Выйти из аккаунта", b"logout")])

        text = (
            f"🏠 **Главное меню**\n\n"
            f"✅ Аккаунт: {name}{uname}\n"
            f"🆔 ID: {me.id}\n"
        )
        if watch_text:
            text += f"\n{watch_text}\n"
    else:
        buttons = [
            [Button.inline("🔑 Войти в аккаунт", b"login")],
        ]
        text = (
            "👋 **Привет! Я бот для отслеживания онлайн-статуса в Telegram.**\n\n"
            "🔐 Для начала нужно войти в аккаунт."
        )

    await event.respond(text, buttons=buttons, parse_mode="md")


def get_status_key(status):
    """Возвращает ключ настройки для типа статуса."""
    if isinstance(status, UserStatusOnline):
        return "online"
    elif isinstance(status, UserStatusOffline):
        return "offline"
    elif isinstance(status, UserStatusRecently):
        return "recently"
    elif isinstance(status, UserStatusLastWeek):
        return "weekly"
    elif isinstance(status, UserStatusLastMonth):
        return "monthly"
    return None


async def send_settings_menu(event):
    def toggle(key, label):
        icon = "✅" if notify_settings[key] else "❌"
        return Button.inline(f"{icon} {label}", f"toggle_{key}".encode())

    buttons = [
        [toggle("online", "🟢 Зашёл в сеть")],
        [toggle("offline", "🔴 Вышел из сети")],
        [toggle("recently", "🟡 Был(а) недавно")],
        [toggle("weekly", "🟠 Был(а) на этой неделе")],
        [toggle("monthly", "🟠 Был(а) в этом месяце")],
        [Button.inline("🔙 Назад в меню", b"menu")],
    ]

    enabled = [k for k, v in notify_settings.items() if v]
    if enabled:
        count = len(enabled)
        text = f"⚙️ **Настройки уведомлений**\n\n🔔 Включено событий: {count}/5\n\n💡 Нажмите на событие, чтобы вкл/выкл:"
    else:
        text = "⚙️ **Настройки уведомлений**\n\n🔕 Все уведомления выключены!\n\n💡 Нажмите на событие, чтобы включить:"

    await event.respond(text, buttons=buttons, parse_mode="md")


async def monitor_loop():
    global last_known_status, watched_username, watched_input_peer

    while True:
        await asyncio.sleep(CHECK_INTERVAL)

        if not watched_username or not watched_input_peer:
            continue

        if not user_client.is_connected() or not await user_client.is_user_authorized():
            logger.warning("User-клиент не авторизован, мониторинг приостановлен.")
            continue

        try:
            result = await user_client(GetUsersRequest([watched_input_peer]))
            user = result[0]
            new_status = user.status
            new_text = format_status(new_status)

            if status_changed(last_known_status, new_status):
                logger.info(f"Статус @{watched_username} изменился: {format_status(last_known_status)} -> {new_text}")
                key = get_status_key(new_status)
                if key and notify_settings.get(key, False):
                    await bot.send_message(
                        ADMIN_ID,
                        f"🔔 **@{watched_username}**\n\n{new_text}",
                        buttons=[
                            [Button.inline("🔍 Проверить ещё раз", b"check_now")],
                            [Button.inline("🏠 Меню", b"menu")],
                        ],
                        parse_mode="md",
                    )
                last_known_status = new_status
            else:
                logger.debug(f"Статус @{watched_username} не изменился: {new_text}")

        except Exception as e:
            logger.error(f"Ошибка при проверке статуса @{watched_username}: {e}")
            await bot.send_message(
                ADMIN_ID,
                f"⚠️ Ошибка при проверке @{watched_username}: {e}",
            )


def register_handlers(bot_client):

    @bot_client.on(events.NewMessage(pattern="/start"))
    async def cmd_start(event):
        if not is_admin(event):
            return
        await send_main_menu(event)

    @bot_client.on(events.CallbackQuery(data=b"menu"))
    async def cb_menu(event):
        if not is_admin(event):
            return
        await send_main_menu(event)

    @bot_client.on(events.CallbackQuery(data=b"status"))
    async def cb_status(event):
        if not is_admin(event):
            return
        if user_client.is_connected() and await user_client.is_user_authorized():
            me = await user_client.get_me()
            name = me.first_name or ""
            if me.last_name:
                name += f" {me.last_name}"
            uname = f" (@{me.username})" if me.username else ""
            await event.answer(f"✅ {name}{uname} | ID: {me.id}", alert=True)
        else:
            await event.answer("❌ Аккаунт не подключён", alert=True)

    @bot_client.on(events.CallbackQuery(data=b"settings"))
    async def cb_settings(event):
        if not is_admin(event):
            return
        await send_settings_menu(event)
        await event.answer()

    @bot_client.on(events.CallbackQuery(pattern=b"toggle_"))
    async def cb_toggle(event):
        if not is_admin(event):
            return
        key = event.data.decode().replace("toggle_", "")
        if key in notify_settings:
            notify_settings[key] = not notify_settings[key]
            state = "✅ Вкл" if notify_settings[key] else "❌ Выкл"
            labels = {
                "online": "🟢 Зашёл в сеть",
                "offline": "🔴 Вышел из сети",
                "recently": "🟡 Был(а) недавно",
                "weekly": "🟠 Был(а) на этой неделе",
                "monthly": "🟠 Был(а) в этом месяце",
            }
            await event.answer(f"{labels[key]}: {state}")
            await send_settings_menu(event)
        else:
            await event.answer("❓ Неизвестная настройка", alert=True)

    @bot_client.on(events.CallbackQuery(data=b"login"))
    async def cb_login(event):
        global login_state
        if not is_admin(event):
            return

        if user_client.is_connected() and await user_client.is_user_authorized():
            await event.answer("✅ Вы уже авторизованы!", alert=True)
            return

        login_state = WAITING_PHONE
        await event.respond(
            "🔑 **Вход в аккаунт**\n\n"
            "📱 Отправьте номер телефона в международном формате:\n"
            "Пример: `+79001234567`",
            buttons=[[Button.inline("❌ Отмена", b"cancel_login")]],
            parse_mode="md",
        )
        await event.answer()

    @bot_client.on(events.CallbackQuery(data=b"cancel_login"))
    async def cb_cancel_login(event):
        global login_state, login_phone, phone_code_hash
        if not is_admin(event):
            return
        login_state = LOGIN_IDLE
        login_phone = None
        phone_code_hash = None
        await event.answer("❌ Вход отменён")
        await send_main_menu(event)

    @bot_client.on(events.CallbackQuery(data=b"watch"))
    async def cb_watch(event):
        global login_state
        if not is_admin(event):
            return

        if not user_client.is_connected() or not await user_client.is_user_authorized():
            await event.answer("❌ Сначала войдите в аккаунт!", alert=True)
            return

        login_state = WAITING_USERNAME
        await event.respond(
            "👁 **Отслеживание пользователя**\n\n"
            "✏️ Отправьте юзернейм пользователя:\n"
            "Пример: `username` или `@username`",
            buttons=[[Button.inline("❌ Отмена", b"cancel_watch")]],
            parse_mode="md",
        )
        await event.answer()

    @bot_client.on(events.CallbackQuery(data=b"cancel_watch"))
    async def cb_cancel_watch(event):
        global login_state
        if not is_admin(event):
            return
        login_state = LOGIN_IDLE
        await event.answer("❌ Отменено")
        await send_main_menu(event)

    @bot_client.on(events.CallbackQuery(data=b"unwatch"))
    async def cb_unwatch(event):
        global watched_username, watched_input_peer, last_known_status
        if not is_admin(event):
            return

        if not watched_username:
            await event.answer("🤷 Никто не отслеживается", alert=True)
            return

        old = watched_username
        watched_username = None
        watched_input_peer = None
        last_known_status = None
        logger.info(f"Остановлено отслеживание @{old}")
        await event.answer(f"🛑 Отслеживание @{old} остановлено")
        await send_main_menu(event)

    @bot_client.on(events.CallbackQuery(data=b"check_now"))
    async def cb_check_now(event):
        global last_known_status
        if not is_admin(event):
            return

        if not watched_username or not watched_input_peer:
            await event.answer("🤷 Никто не отслеживается", alert=True)
            return

        try:
            result = await user_client(GetUsersRequest([watched_input_peer]))
            user = result[0]
            new_status = user.status
            last_known_status = new_status
            status_text = format_status(new_status)

            name = user.first_name or ""
            if user.last_name:
                name += f" {user.last_name}"

            await event.respond(
                f"👤 **@{watched_username}** ({name})\n\n"
                f"📊 Статус: {status_text}",
                buttons=[
                    [Button.inline("🔄 Обновить", b"check_now")],
                    [Button.inline("🏠 Меню", b"menu")],
                ],
                parse_mode="md",
            )
            await event.answer()
        except Exception as e:
            await event.answer(f"⚠️ Ошибка: {e}", alert=True)

    @bot_client.on(events.CallbackQuery(data=b"logout"))
    async def cb_logout(event):
        global login_state, watched_username, watched_input_peer, last_known_status
        if not is_admin(event):
            return

        if not user_client.is_connected() or not await user_client.is_user_authorized():
            await event.answer("❌ Аккаунт не подключён", alert=True)
            return

        if watched_username:
            logger.info(f"Остановлено отслеживание @{watched_username} (logout)")
            watched_username = None
            watched_input_peer = None
            last_known_status = None

        await user_client.log_out()
        login_state = LOGIN_IDLE
        await event.answer("🚪 Вы вышли из аккаунта")
        await send_main_menu(event)

    @bot_client.on(events.NewMessage)
    async def handle_message(event):
        global login_state, login_phone, phone_code_hash
        global watched_username, watched_input_peer, last_known_status

        if not is_admin(event):
            return

        if event.text.startswith("/"):
            return

        # --- Ввод юзернейма для отслеживания ---
        if login_state == WAITING_USERNAME:
            username = event.text.strip().lstrip("@")
            if not username:
                await event.respond("❌ Пустой юзернейм. Попробуйте ещё раз:")
                return

            try:
                entity = await user_client.get_entity(username)
                watched_input_peer = await user_client.get_input_entity(entity)
            except Exception as e:
                await event.respond(
                    f"❌ Не удалось найти **@{username}**\n"
                    f"Убедитесь, что юзернейм верный и у вас есть чат с этим пользователем.\n\n"
                    f"⚠️ Ошибка: `{e}`",
                    buttons=[[Button.inline("🏠 Меню", b"menu")]],
                    parse_mode="md",
                )
                login_state = LOGIN_IDLE
                return

            watched_username = username
            last_known_status = entity.status
            current_status = format_status(entity.status)
            login_state = LOGIN_IDLE

            name = entity.first_name or ""
            if entity.last_name:
                name += f" {entity.last_name}"

            await event.respond(
                f"✅ **Отслеживание запущено!**\n\n"
                f"👤 Пользователь: **@{username}** ({name})\n"
                f"📊 Текущий статус: {current_status}\n"
                f"⏱ Проверка каждые 5 секунд\n\n"
                f"🔔 Уведомление придёт, когда пользователь выйдет в сеть",
                buttons=[
                    [Button.inline("🔍 Проверить сейчас", b"check_now")],
                    [Button.inline("🛑 Остановить", b"unwatch")],
                    [Button.inline("🏠 Меню", b"menu")],
                ],
                parse_mode="md",
            )
            logger.info(f"Начато отслеживание @{username}")
            return

        # --- Ввод номера телефона ---
        if login_state == WAITING_PHONE:
            phone = event.text.strip()
            if not phone.startswith("+") or not phone[1:].isdigit():
                await event.respond(
                    "❌ Неверный формат. Используйте:\n`+79001234567`",
                    parse_mode="md",
                )
                return

            login_phone = phone
            await event.respond("📤 Отправляю код подтверждения...")

            try:
                if not user_client.is_connected():
                    await user_client.connect()

                result = await user_client.send_code_request(phone)
                phone_code_hash = result.phone_code_hash
                login_state = WAITING_CODE
                await event.respond(
                    "✉️ **Код отправлен!**\n\n"
                    "Введите код подтверждения из Telegram.\n"
                    "💡 Формат: цифры через пробел или дефис\n"
                    "Пример: `1 2 3 4 5` или `1-2-3-4-5`",
                    buttons=[[Button.inline("❌ Отмена", b"cancel_login")]],
                    parse_mode="md",
                )
            except FloodWaitError as e:
                await event.respond(
                    f"⏳ Слишком много попыток. Подождите {e.seconds} сек.",
                    buttons=[[Button.inline("🏠 Меню", b"menu")]],
                )
                login_state = LOGIN_IDLE
            except Exception as e:
                logger.error(f"Ошибка при отправке кода: {e}")
                await event.respond(
                    f"⚠️ Ошибка: {e}",
                    buttons=[[Button.inline("🏠 Меню", b"menu")]],
                )
                login_state = LOGIN_IDLE
            return

        # --- Ввод кода подтверждения ---
        if login_state == WAITING_CODE:
            code = "".join(c for c in event.text if c.isdigit())

            if not code or len(code) < 4:
                await event.respond("❌ Введите корректный код (минимум 4 цифры).")
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
                await event.respond(
                    f"🎉 **Вход выполнен!**\n\nДобро пожаловать, **{name}**! 👋",
                    buttons=[
                        [Button.inline("👁 Отслеживать пользователя", b"watch")],
                        [Button.inline("🏠 Меню", b"menu")],
                    ],
                    parse_mode="md",
                )

            except SessionPasswordNeededError:
                login_state = WAITING_PASSWORD
                await event.respond(
                    "🔒 **Двухфакторная аутентификация**\n\n"
                    "Введите облачный пароль:",
                    buttons=[[Button.inline("❌ Отмена", b"cancel_login")]],
                    parse_mode="md",
                )
            except PhoneCodeInvalidError:
                await event.respond("❌ Неверный код. Попробуйте ещё раз:")
            except PhoneCodeExpiredError:
                await event.respond(
                    "⏰ Код истёк.",
                    buttons=[[Button.inline("🔑 Попробовать снова", b"login")]],
                )
                login_state = LOGIN_IDLE
            except FloodWaitError as e:
                await event.respond(f"⏳ Подождите {e.seconds} сек.")
                login_state = LOGIN_IDLE
            except Exception as e:
                logger.error(f"Ошибка при вводе кода: {e}")
                await event.respond(f"⚠️ Ошибка: {e}")
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
                await event.respond(
                    f"🎉 **Вход выполнен!**\n\nДобро пожаловать, **{name}**! 👋",
                    buttons=[
                        [Button.inline("👁 Отслеживать пользователя", b"watch")],
                        [Button.inline("🏠 Меню", b"menu")],
                    ],
                    parse_mode="md",
                )

            except PasswordHashInvalidError:
                await event.respond("❌ Неверный пароль. Попробуйте ещё раз:")
            except FloodWaitError as e:
                await event.respond(f"⏳ Подождите {e.seconds} сек.")
                login_state = LOGIN_IDLE
            except Exception as e:
                logger.error(f"Ошибка при вводе пароля: {e}")
                await event.respond(f"⚠️ Ошибка: {e}")
                login_state = LOGIN_IDLE
            return


async def main():
    global bot, user_client

    logger.info("🚀 Запуск бота...")

    bot = TelegramClient("bot_session", API_ID, API_HASH)
    user_client = TelegramClient("user_session", API_ID, API_HASH)

    register_handlers(bot)

    await bot.start(bot_token=BOT_TOKEN)
    logger.info("✅ Бот запущен.")

    try:
        await user_client.connect()
        if await user_client.is_user_authorized():
            me = await user_client.get_me()
            logger.info(f"✅ User-клиент подключён: {me.first_name} (ID: {me.id})")
        else:
            logger.info("⏳ User-клиент не авторизован. Используйте /start в боте.")
    except Exception as e:
        logger.warning(f"⚠️ Не удалось подключить user-клиент: {e}")

    asyncio.create_task(monitor_loop())
    logger.info("👁 Фоновый мониторинг запущен (интервал: 5 сек).")

    logger.info("🟢 Бот готов к работе. Нажмите Ctrl+C для остановки.")
    await bot.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
