from __future__ import annotations

import hashlib

from shadowtrace.utils.validators import validate_email


def gravatar_url(email: str) -> str:
    normalized = validate_email(email).strip().lower()
    digest = hashlib.md5(normalized.encode()).hexdigest()
    return f"https://www.gravatar.com/avatar/{digest}?d=404"
