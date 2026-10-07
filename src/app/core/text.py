def collapse_spaces(value: str) -> str:
    """Убирает пробелы по краям и схлопывает внутренние"""
    return " ".join(value.split())


def normalize_name(value: str) -> str:
    """Нормализация названий жанров и авторов: пробелы и регистр"""
    return collapse_spaces(value).title()


def normalize_email(value: str) -> str:
    return value.strip().lower()