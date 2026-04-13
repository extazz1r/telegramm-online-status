def format_user_name(user) -> str:
    """Форматирует имя пользователя Telegram.

    Принимает объект user от Telethon (me = await client.get_me()).
    """
    name = user.first_name or ""
    if user.last_name:
        name += f" {user.last_name}"
    return name


def format_user_info(user) -> str:
    """Форматирует полную информацию о пользователе для /status."""
    name = format_user_name(user)
    username = f" (@{user.username})" if user.username else ""
    return f"Аккаунт подключён: {name}{username}\nID: {user.id}"
