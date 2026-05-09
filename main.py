#!/usr/bin/env python3
from __future__ import annotations

import asyncio

from shadowtrace.cli.menu import main


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
