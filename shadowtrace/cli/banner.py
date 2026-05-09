from __future__ import annotations

from rich.panel import Panel

from shadowtrace.core.logger import console


def banner() -> None:
    console.print(Panel.fit(
        """
ShadowTrace v4.0 🚀 [light_blue]MODULAR OSINT TOOLKIT[/light_blue]
[cyan]https://github.com/Misterydo/shadowtrace[/cyan]
Ethical hacking only. CLI by professionals, for professionals.
""",
        style="magenta",
    ))
