from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any

from shadowtrace.core.logger import console


def export_html(profiles: list[dict[str, Any]], path: str | Path) -> None:
    target = Path(path)
    chunks = [
        """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>ShadowTrace OSINT Report</title>
<style>
body { font-family: Arial, sans-serif; background: #f3f4f6; color: #111827; }
.profile { background: #fff; margin: 1em auto; padding: 1em; border-radius: 8px; max-width: 980px; box-shadow: 0 1px 4px #0002; }
.found { color: #15803d; font-weight: bold; }
.not-found { color: #b91c1c; font-weight: bold; }
pre { white-space: pre-wrap; background: #f9fafb; padding: .75em; border-radius: 6px; }
a { color: #2563eb; }
</style>
</head>
<body>
<h1>ShadowTrace OSINT Report</h1>
"""
    ]
    for profile in profiles:
        found = profile.get("status") == "FOUND"
        status_class = "found" if found else "not-found"
        metadata = escape(json.dumps(profile.get("metadata", {}), indent=2, ensure_ascii=False))
        url = escape(profile.get("url", ""))
        chunks.append(f"""
<section class="profile">
<strong>Site:</strong> {escape(profile.get('site', ''))}<br>
<strong>Username:</strong> {escape(profile.get('username', ''))}<br>
<strong>Status:</strong> <span class="{status_class}">{escape(profile.get('status', ''))}</span><br>
<strong>Confidence:</strong> {profile.get('confidence', 0)}%<br>
<strong>Avatar hash:</strong> {escape(str(profile.get('avatar_hash') or ''))}<br>
<strong>Lang:</strong> {escape(str(profile.get('metadata', {}).get('lang_bio', '')))}<br>
<strong>Profile:</strong> <a href="{url}">{url}</a><br>
<strong>Metadata:</strong><pre>{metadata}</pre>
</section>
""")
    chunks.append("</body></html>")
    target.write_text("".join(chunks), encoding="utf-8")
    console.print(f"[green]HTML report saved as {target}")
