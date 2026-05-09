# ShadowTrace

ShadowTrace is a modular OSINT username investigation toolkit for Linux-friendly environments. The project was refactored from a single script into a maintainable package with isolated scraping modules, reusable HTTP/session infrastructure, cache support, structured exports, and an interactive or argument-driven CLI.

> Use ShadowTrace only for lawful, ethical, and authorized research.

## Features

- Modular extractors for GitHub, Instagram, X/Twitter, and Reddit.
- Passive intelligence mode using Bing dorks with SQLite TTL cache.
- Centralized configuration in `shadowtrace_config.json`.
- Shared async `aiohttp` session manager with redirect support, timeouts, retry/backoff, realistic rotating headers, and response-size limits.
- SQLite cache with WAL mode for discovered profiles, timeline entries, avatar hashes, and passive search results.
- JSON, CSV, HTML, and GraphML exports.
- Rich terminal UI with colored logs and progress bars.
- Extension registry for future plugins/modules.
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

## Adding a new module

1. Create a new extractor in `shadowtrace/modules/<platform>.py` inheriting from `BaseExtractor`.
2. Implement `extract_metadata`, `fingerprint`, and optionally `confidence`.
3. Register it in `shadowtrace/modules/registry.py` with a URL template.

Minimal extractor skeleton:

```python
from shadowtrace.modules.base import BaseExtractor

class ExampleExtractor(BaseExtractor):
    site_name = "Example"
    url_patterns = ("example.com",)

    async def extract_metadata(self, html: str) -> dict[str, object]:
        return {}
```

## Security and stability notes

- Responses are capped by `max_response_bytes` to reduce memory pressure.
- Requests use `allow_redirects=True` and a centralized `aiohttp.ClientTimeout`.
- Passive search uses a rate limit plus jitter to reduce blocking.
- Challenge/captcha pages are detected and not treated as valid profiles.

## Roadmap / TODO

- Formal plugin discovery from a `plugins/` directory.
- Optional encrypted profiles and per-investigation workspaces.
- Smarter adaptive rate limiting per host and per HTTP status.
- Pluggable cache backends beyond SQLite.
- Optional Tor health checks and proxy scoring.
- Unit tests with recorded HTTP fixtures.
- More platform modules and verified API integrations where permitted.

## License

See [LICENSE](LICENSE).
