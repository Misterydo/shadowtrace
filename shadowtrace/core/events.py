from __future__ import annotations

import inspect
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

EventHandler = Callable[["Event"], Awaitable[None] | None]


@dataclass(slots=True)
class Event:
    name: str
    payload: dict[str, Any] = field(default_factory=dict)


class EventBus:
    """Small async hook system used by modules, plugins and future UIs/APIs."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_name: str, handler: EventHandler) -> None:
        self._handlers[event_name].append(handler)

    async def emit(self, event_name: str, **payload: Any) -> None:
        event = Event(event_name, payload)
        for handler in [*self._handlers.get(event_name, []), *self._handlers.get("*", [])]:
            result = handler(event)
            if inspect.isawaitable(result):
                await result


event_bus = EventBus()
