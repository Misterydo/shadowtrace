# ShadowTrace

ShadowTrace is a modular OSINT username investigation toolkit for Linux-friendly environments. The project was refactored from a single script into a maintainable package with isolated scraping modules, reusable HTTP/session infrastructure, cache support, structured exports, and an interactive or argument-driven CLI.

> Use ShadowTrace only for lawful, ethical, and authorized research.

## Features

- Modular extractors for GitHub, Instagram, X/Twitter, and Reddit with a standard module lifecycle (`validate`, `collect`, `parse`, `normalize`, `enrich`, `correlate`, `run`).
- Passive intelligence mode using Bing dorks with SQLite TTL cache.
- Centralized configuration in `shadowtrace_config.json`.
- Shared async `aiohttp` session manager with redirect support, timeouts, retry/backoff, realistic rotating headers, and response-size limits.
- SQLite cache with WAL mode for discovered profiles, timeline entries, avatar hashes, and passive search results.
- JSON, CSV, HTML, and GraphML exports.
- Rich terminal UI with colored logs and progress bars.
- Runtime module registry and plugin discovery that can load new modules without changing the core engine.
- Async event hooks, global/per-module rate limiting, target typing, module priorities, standardized artifacts, universal platform profiles, risk scores, and correlation-ready outputs.
- Optional Tor/proxy-ready configuration.

## Project layout

```text
shadowtrace/
├── cli/                # Interactive menu and argparse entry points
├── core/               # Engine, config, cache, session and async orchestration
├── modules/            # Platform-specific OSINT extractors and passive intel
├── output/             # JSON, CSV, HTML and GraphML exporters
└── utils/              # Parsing, validation, retry, formatting and fingerprints
```

Top-level entry points:

- `main.py` — primary launcher.
- `ShadowTrace.py` — backward-compatible launcher for older workflows.

## Installation

```bash
git clone https://github.com/Misterydo/shadowtrace.git
cd shadowtrace
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

Interactive mode:

```bash
python main.py
```

One-shot scan:

```bash
python main.py scan username
```

Scan username variants:

```bash
python main.py scan username --variants
```

Enable passive enrichment:

```bash
python main.py scan username --passive
```

Export results:

```bash
python main.py scan username --json report.json --html report.html --graphml graph.graphml
```

## Configuration

The first run creates `shadowtrace_config.json` with defaults:

```json
{
  "timeout": 10,
  "threads": 6,
  "stealth": true,
  "tor": false,
  "proxy_list": [],
  "mode": "passive",
  "max_retries": 2,
  "sem_delay_ms": [300, 2000],
  "passive_ttl_hours": 24,
  "passive_rate_limit_sec": 5.0,
  "max_response_bytes": 2000000
}
```

### Tor and proxies

Set `tor` to `true` to route through `socks5://127.0.0.1:9050`, or provide proxy URLs in `proxy_list`. SOCKS proxies require `aiohttp-socks`.

## Architecture for large-scale OSINT expansion

ShadowTrace is now prepared to evolve beyond username lookup into a professional modular OSINT framework. The core model supports target types such as usernames, emails, phones, domains, URLs, IOCs, cryptocurrency wallets, documents, images, and social profiles. Modules declare capabilities such as social scraping, GitHub intelligence, metadata extraction, breach analysis, DNS/WHOIS/subdomain enumeration, URL intelligence, reputation analysis, risk scoring, timeline generation, and profile correlation.

The engine is intentionally decoupled from module internals:

- `ModuleRegistry` stores built-in and plugin modules at runtime.
- `BaseExtractor`/`PlatformModule` define a phased lifecycle: `check_exists()`, `extract_basic()`, `extract_advanced()`, `normalize()`, `enrich()`, `correlate()`, and `run()`.
- `UniversalProfile` keeps every platform on the same schema: platform, existence, username, display name, bio, avatar, followers/following/posts, verification, external links, confidence, and raw metadata.
- `ModuleResult` and `IntelligenceArtifact` provide standardized outputs for future REST APIs, web UI, databases, queues, and distributed workers.
- `EventBus` exposes hooks such as `engine.initialized`, `module.started`, `module.completed`, `module.failed`, and pipeline events for integrations.
- `AsyncRateLimiter` supports global and per-module rate limits.
- Module priorities allow future queue/worker execution plans to run high-value modules first.

Platform modules can implement custom logic for their specific public exposure model instead of only checking existence. For example, Instagram can normalize hashtags, mentions, external links and dorks; X/Twitter can focus on tweets, replies, timestamps and shared URLs; Reddit can model subreddits, karma and temporal behavior; GitHub can model commits, leaked commit emails, organizations, repositories and development fingerprints.

## Adding a new module or plugin

1. Create a module inheriting from `BaseExtractor`.
2. Declare `name`, `description`, `target_types`, `capabilities`, `kind`, and `priority`.
3. Implement the lifecycle methods needed by that module. Simple modules can implement only `extract_metadata()` and `fingerprint()`; advanced modules can add custom collectors, parsers, normalizers, enrichers and correlators.
4. Place plugin files in a configured `plugin_paths` directory and expose `MODULE`, `MODULES`, or legacy `EXTRACTOR`. The core engine will discover them at startup.

Minimal plugin skeleton:

```python
from shadowtrace.core.models import ModuleCapability, ModuleKind, ModulePriority, TargetType
from shadowtrace.modules.base import BaseExtractor

class ExampleModule(BaseExtractor):
    name = "Example"
    description = "Example platform intelligence"
    target_types = (TargetType.USERNAME,)
    capabilities = (ModuleCapability.USERNAME_LOOKUP, ModuleCapability.SOCIAL_SCRAPING)
    kind = ModuleKind.PASSIVE
    priority = ModulePriority.NORMAL
    url_patterns = ("example.com",)
    url_template = "https://example.com/{}"

    async def extract_metadata(self, html: str) -> dict[str, object]:
        return {}

MODULE = ExampleModule()
```

## Security and stability notes

- Responses are capped by `max_response_bytes` to reduce memory pressure.
- Requests use `allow_redirects=True` and a centralized `aiohttp.ClientTimeout`.
- Passive search uses a rate limit plus jitter to reduce blocking.
- Challenge/captcha pages are detected and not treated as valid profiles.

## Roadmap / TODO

- API REST and web UI backed by standardized module results.
- Optional encrypted profiles and per-investigation workspaces.
- Smarter adaptive rate limiting per host and per HTTP status.
- Pluggable cache backends beyond SQLite.
- Optional Tor health checks and proxy scoring.
- Unit tests with recorded HTTP fixtures.
- More platform modules and verified API integrations where permitted.
- Avatar hash, semantic bio, external-link and username-variant enrichers feeding the universal correlation score.

## License

See [LICENSE](LICENSE).
