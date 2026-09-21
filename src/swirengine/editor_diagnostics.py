from __future__ import annotations

import logging
import time
from collections import Counter, deque
from dataclasses import dataclass
from threading import RLock

from .profiler import FrameProfile, Profiler

_CONSOLE_LEVELS = {"debug", "info", "warning", "error", "critical"}


@dataclass(frozen=True, slots=True)
class EditorConsoleEntry:
    """One immutable console message exposed to visual-editor front-ends."""

    sequence: int
    timestamp: float
    level: str
    message: str
    source: str = "runtime"
    path: str | None = None
    line: int | None = None
    column: int | None = None

    @property
    def has_source_location(self) -> bool:
        return self.path is not None


@dataclass(frozen=True, slots=True)
class EditorConsoleFrame:
    """Filtered console snapshot suitable for rendering in one editor frame."""

    entries: tuple[EditorConsoleEntry, ...]
    total_entries: int
    counts: tuple[tuple[str, int], ...]
    query: str = ""
    levels: tuple[str, ...] = ()
    source: str | None = None

    @property
    def error_count(self) -> int:
        return sum(count for level, count in self.counts if level in {"error", "critical"})

    @property
    def warning_count(self) -> int:
        return sum(count for level, count in self.counts if level == "warning")


class _EditorLoggingHandler(logging.Handler):
    def __init__(self, console: EditorConsole) -> None:
        super().__init__()
        self.console = console

    def emit(self, record: logging.LogRecord) -> None:
        message = self.format(record)
        self.console.write(
            message,
            level=record.levelname.lower(),
            source=record.name or "logging",
            timestamp=record.created,
            path=record.pathname or None,
            line=record.lineno if record.lineno > 0 else None,
        )


class EditorConsole:
    """Bounded, thread-safe runtime console model for the visual editor.

    Messages can be pushed directly or captured from the standard ``logging`` module through
    ``logging_handler``. Filtering is snapshot-based, so GUI front-ends never need to mutate or
    iterate over the live deque while game/runtime threads are producing messages. Optional source
    locations let creator front-ends provide safe click-through navigation without parsing message
    strings.
    """

    def __init__(self, *, history: int = 1000) -> None:
        if history < 1:
            raise ValueError("history must be at least 1")
        self.history = int(history)
        self._entries: deque[EditorConsoleEntry] = deque(maxlen=self.history)
        self._next_sequence = 1
        self._lock = RLock()
        self._handler: _EditorLoggingHandler | None = None

    @property
    def entries(self) -> tuple[EditorConsoleEntry, ...]:
        with self._lock:
            return tuple(self._entries)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def write(
        self,
        message: object,
        *,
        level: str = "info",
        source: str = "runtime",
        timestamp: float | None = None,
        path: str | None = None,
        line: int | None = None,
        column: int | None = None,
    ) -> EditorConsoleEntry:
        normalized_level = level.strip().lower()
        if normalized_level not in _CONSOLE_LEVELS:
            raise ValueError(f"unsupported console level {level!r}")
        normalized_source = source.strip()
        if not normalized_source:
            raise ValueError("console source cannot be empty")
        normalized_path = None if path is None else str(path).strip()
        if normalized_path == "":
            raise ValueError("console source path cannot be empty")
        if line is not None and line < 1:
            raise ValueError("console source line must be at least 1")
        if column is not None and column < 1:
            raise ValueError("console source column must be at least 1")
        if normalized_path is None and (line is not None or column is not None):
            raise ValueError("console source line/column requires a source path")
        entry_timestamp = time.time() if timestamp is None else float(timestamp)
        entry_message = str(message)
        with self._lock:
            entry = EditorConsoleEntry(
                self._next_sequence,
                entry_timestamp,
                normalized_level,
                entry_message,
                normalized_source,
                normalized_path,
                line,
                column,
            )
            self._next_sequence += 1
            self._entries.append(entry)
        return entry

    def frame(
        self,
        *,
        query: str = "",
        levels: tuple[str, ...] | None = None,
        source: str | None = None,
        limit: int | None = None,
    ) -> EditorConsoleFrame:
        normalized_query = query.strip().casefold()
        normalized_levels: tuple[str, ...] = ()
        if levels is not None:
            unique: list[str] = []
            for level in levels:
                normalized = level.strip().lower()
                if normalized not in _CONSOLE_LEVELS:
                    raise ValueError(f"unsupported console level {level!r}")
                if normalized not in unique:
                    unique.append(normalized)
            normalized_levels = tuple(unique)
        normalized_source = None if source is None else source.strip()
        if normalized_source == "":
            normalized_source = None
        if limit is not None and limit < 1:
            raise ValueError("console frame limit must be at least 1")

        with self._lock:
            all_entries = tuple(self._entries)
        counts = Counter(entry.level for entry in all_entries)
        filtered = tuple(
            entry
            for entry in all_entries
            if (not normalized_levels or entry.level in normalized_levels)
            and (normalized_source is None or entry.source == normalized_source)
            and (
                not normalized_query
                or normalized_query in entry.message.casefold()
                or normalized_query in entry.source.casefold()
                or (entry.path is not None and normalized_query in entry.path.casefold())
            )
        )
        if limit is not None:
            filtered = filtered[-limit:]
        return EditorConsoleFrame(
            filtered,
            len(all_entries),
            tuple((level, counts.get(level, 0)) for level in sorted(_CONSOLE_LEVELS)),
            normalized_query,
            normalized_levels,
            normalized_source,
        )

    def logging_handler(self, *, formatter: logging.Formatter | None = None) -> logging.Handler:
        """Return one reusable ``logging.Handler`` that feeds this console."""

        with self._lock:
            if self._handler is None:
                self._handler = _EditorLoggingHandler(self)
            handler = self._handler
        if formatter is not None:
            handler.setFormatter(formatter)
        return handler


@dataclass(frozen=True, slots=True)
class EditorProfilerFrame:
    """Derived profiler metrics for the visual editor Profiler panel."""

    latest: FrameProfile
    average: FrameProfile
    peak_frame_ms: float
    peak_cpu_ms: float
    minimum_fps: float
    sample_count: int
    frame_budget_ms: float
    over_budget_frames: int

    @property
    def over_budget_ratio(self) -> float:
        if self.sample_count == 0:
            return 0.0
        return self.over_budget_frames / self.sample_count

    @property
    def frame_budget_ok(self) -> bool:
        return self.latest.frame_ms <= self.frame_budget_ms


class EditorProfiler:
    """Read-only analytical view over the runtime ``Profiler`` history."""

    def __init__(
        self,
        profiler: Profiler,
        *,
        window: int = 60,
        target_fps: float = 60.0,
    ) -> None:
        if window < 1:
            raise ValueError("profiler window must be at least 1")
        if target_fps <= 0:
            raise ValueError("target_fps must be greater than zero")
        self.profiler = profiler
        self.window = int(window)
        self.target_fps = float(target_fps)

    @property
    def frame_budget_ms(self) -> float:
        return 1000.0 / self.target_fps

    def configure(self, *, window: int | None = None, target_fps: float | None = None) -> None:
        if window is not None:
            if window < 1:
                raise ValueError("profiler window must be at least 1")
            self.window = int(window)
        if target_fps is not None:
            if target_fps <= 0:
                raise ValueError("target_fps must be greater than zero")
            self.target_fps = float(target_fps)

    def frame(self) -> EditorProfilerFrame:
        samples = self.profiler.samples[-self.window :]
        budget = self.frame_budget_ms
        if not samples:
            empty = FrameProfile()
            return EditorProfilerFrame(empty, empty, 0.0, 0.0, 0.0, 0, budget, 0)
        average = self.profiler.average(len(samples))
        return EditorProfilerFrame(
            samples[-1],
            average,
            max(sample.frame_ms for sample in samples),
            max(sample.cpu_ms for sample in samples),
            min(sample.fps for sample in samples),
            len(samples),
            budget,
            sum(sample.frame_ms > budget for sample in samples),
        )
