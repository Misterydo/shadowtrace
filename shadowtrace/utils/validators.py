from __future__ import annotations

import re
from email_validator import EmailNotValidError, validate_email as _validate_email

USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def validate_username(username: str) -> str:
    value = username.strip().lstrip("@")
    if not USERNAME_RE.match(value):
        raise ValueError("Username inválido. Use letras, números, ponto, hífen ou underscore.")
    return value


def validate_email(email: str) -> str:
    try:
        return _validate_email(email, check_deliverability=False).normalized
    except EmailNotValidError as exc:
        raise ValueError(str(exc)) from exc
