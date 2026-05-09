from __future__ import annotations

import hashlib
from io import BytesIO

import imagehash
from PIL import Image


def hash_avatar(image_bytes: bytes) -> tuple[str | None, str | None]:
    try:
        img = Image.open(BytesIO(image_bytes))
        return str(imagehash.phash(img)), hashlib.md5(image_bytes).hexdigest()
    except Exception:
        return None, None


def extract_avatar_url(metadata: dict[str, object]) -> str | None:
    for key in ("avatar_url", "og_image", "profile_pic"):
        value = metadata.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def entropic_score(username: str) -> int:
    return min(100, int(10 * len(set(username)) / max(1, len(username))))
