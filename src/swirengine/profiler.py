from __future__ import annotations

import time
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from typing import ClassVar


@dataclass(frozen=True, slots=True)
class FrameProfile:
    frame_ms: float = 0.0
    cpu_ms: float = 0.0
    fps: float = 0.0
    update_ms: float = 0.0
    physics_ms: float = 0.0
    render_ms: float = 0.0
    draw_calls: int = 0
    sprites: int = 0
    sprite_batches: int = 0
    triangles: int = 0


class Profiler:
    """Low-overhead frame profiler used by the runtime and debug overlay."""

    _KNOWN_SECTIONS: ClassVar[frozenset[str]] = frozenset({"update", "physics", "render"})

    def __init__(self, *, history: int = 120, enabled: bool = True) -> None:
        if history < 1:
            raise ValueError("history must be at least 1")
        self.enabled = bool(enabled)
        self._history: deque[FrameProfile] = deque(maxlen=int(history))
        self._frame_started = 0.0
        self._sections: dict[str, float] = {}

    @property
    def latest(self) -> FrameProfile:
        return self._history[-1] if self._history else FrameProfile()

    @property
    def samples(self) -> tuple[FrameProfile, ...]:
        return tuple(self._history)

    def clear(self) -> None:
        self._history.clear()
        self._sections.clear()
        self._frame_started = 0.0

    def begin_frame(self) -> None:
        if not self.enabled:
            return
        self._sections.clear()
        self._frame_started = time.perf_counter()

    def record(self, section: str, seconds: float) -> None:
        if not self.enabled:
            return
        if section not in self._KNOWN_SECTIONS:
            raise ValueError(f"unknown profiler section: {section}")
        self._sections[section] = self._sections.get(section, 0.0) + max(0.0, float(seconds))

    @contextmanager
    def measure(self, section: str) -> Iterator[None]:
        if section not in self._KNOWN_SECTIONS:
            raise ValueError(f"unknown profiler section: {section}")
        if not self.enabled:
            yield
            return
        started = time.perf_counter()
        try:
            yield
        finally:
            self.record(section, time.perf_counter() - started)

    def end_frame(self, frame_seconds: float, renderer_stats: object | None = None) -> FrameProfile:
        if not self.enabled:
            return FrameProfile()

        frame_seconds = max(0.0, float(frame_seconds))
        cpu_ms = 0.0
        if self._frame_started > 0.0:
            cpu_ms = max(0.0, (time.perf_counter() - self._frame_started) * 1000.0)

        profile = FrameProfile(
            frame_ms=frame_seconds * 1000.0,
            cpu_ms=cpu_ms,
            fps=(1.0 / frame_seconds) if frame_seconds > 0.0 else 0.0,
            update_ms=self._sections.get("update", 0.0) * 1000.0,
            physics_ms=self._sections.get("physics", 0.0) * 1000.0,
            render_ms=self._sections.get("render", 0.0) * 1000.0,
        )
        if renderer_stats is not None:
            profile = replace(
                profile,
                draw_calls=int(getattr(renderer_stats, "draw_calls", 0)),
                sprites=int(getattr(renderer_stats, "sprites", 0)),
                sprite_batches=int(getattr(renderer_stats, "sprite_batches", 0)),
                triangles=int(getattr(renderer_stats, "triangles", 0)),
            )
        self._history.append(profile)
        return profile

    def average(self, count: int | None = None) -> FrameProfile:
        samples = tuple(self._history)
        if count is not None:
            if count < 1:
                raise ValueError("count must be at least 1")
            samples = samples[-count:]
        if not samples:
            return FrameProfile()

        size = len(samples)
        return FrameProfile(
            frame_ms=sum(item.frame_ms for item in samples) / size,
            cpu_ms=sum(item.cpu_ms for item in samples) / size,
            fps=sum(item.fps for item in samples) / size,
            update_ms=sum(item.update_ms for item in samples) / size,
            physics_ms=sum(item.physics_ms for item in samples) / size,
            render_ms=sum(item.render_ms for item in samples) / size,
            draw_calls=round(sum(item.draw_calls for item in samples) / size),
            sprites=round(sum(item.sprites for item in samples) / size),
            sprite_batches=round(sum(item.sprite_batches for item in samples) / size),
            triangles=round(sum(item.triangles for item in samples) / size),
        )
