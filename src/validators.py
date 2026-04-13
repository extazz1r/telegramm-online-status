def validate_phone(phone: str) -> str | None:
    """Проверяет формат номера телефона.

    Возвращает None если номер корректный,
    иначе текст ошибки.
    """
    phone = phone.strip()
    if not phone.startswith("+"):
        return "Неверный формат номера. Используйте международный формат, например: +79001234567"
    if not phone[1:].isdigit():
        return "Неверный формат номера. Используйте международный формат, например: +79001234567"
    if len(phone) < 7:
        return "Номер слишком короткий. Используйте международный формат, например: +79001234567"
    return None


def parse_code(raw: str) -> str | None:
    """Извлекает цифры из строки с кодом подтверждения.

    Возвращает строку цифр если код валидный (>= 4 цифры),
    иначе None.
    """
    code = "".join(c for c in raw if c.isdigit())
    if not code or len(code) < 4:
        return None
    return code
