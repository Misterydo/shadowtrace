from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from shadowtrace.core.logger import console


def export_json(profiles: list[dict[str, Any]], path: str | Path) -> None:
    target = Path(path)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(profiles, handle, indent=2, ensure_ascii=False)
    console.print(f"[green]Exported JSON to {target}")
