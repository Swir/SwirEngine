from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self._listeners: dict[str, list[Callable[..., Any]]] = defaultdict(list)

    def on(self, event: str, callback: Callable[..., Any]) -> Callable[..., Any]:
        self._listeners[event].append(callback)
        return callback

    def off(self, event: str, callback: Callable[..., Any]) -> None:
        if callback in self._listeners.get(event, []):
            self._listeners[event].remove(callback)

    def emit(self, event: str, *args: Any, **kwargs: Any) -> None:
        for callback in tuple(self._listeners.get(event, ())):
            callback(*args, **kwargs)

    def clear(self) -> None:
        self._listeners.clear()
