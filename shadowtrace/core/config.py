from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[2]
CONFIG_FILE = BASE_DIR / "shadowtrace_config.json"
DB_FILE = BASE_DIR / "shadowtrace.sqlite3"


@dataclass(slots=True)
class ShadowTraceConfig:
    timeout: int = 10
    threads: int = 6
    stealth: bool = True
    tor: bool = False
    proxy_list: list[str] = field(default_factory=list)
    mode: str = "passive"
    max_retries: int = 2
    sem_delay_ms: tuple[int, int] = (300, 2000)
    passive_ttl_hours: int = 24
    passive_rate_limit_sec: float = 5.0
    global_rate_limit_sec: float = 0.0
    module_rate_limits_sec: dict[str, float] = field(default_factory=dict)
    plugin_paths: list[str] = field(default_factory=lambda: ["plugins"])
    max_response_bytes: int = 2_000_000
    debug_html_dump: bool = False
    debug_dir: str = "debug"
    user_agents: list[str] = field(default_factory=lambda: [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121 Safari/537.36",
    ])
    accept_headers: list[str] = field(default_factory=lambda: [
        "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "application/json;q=0.9,text/plain;q=0.8,*/*;q=0.7",
    ])
    referers: list[str] = field(default_factory=lambda: [
        "https://www.google.com/", "https://duckduckgo.com/", "https://www.bing.com/",
    ])
    sec_ch_ua_headers: list[str] = field(default_factory=lambda: [
        '"Chromium";v="121", "Not:A-Brand";v="8"',
        '"Google Chrome";v="120", "Chromium";v="120", "Not:A-Brand";v="24"',
    ])

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "ShadowTraceConfig":
        defaults = asdict(cls())
        defaults.update(data)
        if isinstance(defaults.get("sem_delay_ms"), list):
            defaults["sem_delay_ms"] = tuple(defaults["sem_delay_ms"])
        return cls(**{k: defaults[k] for k in cls.__dataclass_fields__})

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["sem_delay_ms"] = list(self.sem_delay_ms)
        return data

    def proxy(self) -> str | None:
        if self.tor:
            return "socks5://127.0.0.1:9050"
        if self.proxy_list:
            import random
            return random.choice(self.proxy_list)
        return None


def load_config(path: Path = CONFIG_FILE) -> ShadowTraceConfig:
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            return ShadowTraceConfig.from_mapping(json.load(handle))
    config = ShadowTraceConfig()
    save_config(config, path)
    return config


def save_config(config: ShadowTraceConfig, path: Path = CONFIG_FILE) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(config.to_json(), handle, indent=4, ensure_ascii=False)


CONFIG = load_config()
