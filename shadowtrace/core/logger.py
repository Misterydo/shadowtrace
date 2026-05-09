from __future__ import annotations

import logging
from rich.console import Console
from rich.logging import RichHandler

console = Console()


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True, markup=True)],
    )
    return logging.getLogger("shadowtrace")


logger = configure_logging()
