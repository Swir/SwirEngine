from __future__ import annotations

import logging

import pytest

from swirengine.editor_diagnostics import EditorConsole, EditorProfiler
from swirengine.profiler import Profiler


def test_console_is_bounded_and_assigns_monotonic_sequences() -> None:
    console = EditorConsole(history=2)

    first = console.write("first", level="debug", timestamp=1.0)
    second = console.write("second", timestamp=2.0)
    third = console.write("third", level="warning", timestamp=3.0)

    assert first.sequence == 1
    assert second.sequence == 2
    assert third.sequence == 3
    assert [entry.message for entry in console.entries] == ["second", "third"]


def test_console_frame_filters_query_level_source_and_limit() -> None:
    console = EditorConsole()
    console.write("asset loaded", source="assets", timestamp=1.0)
    console.write("texture warning", level="warning", source="renderer", timestamp=2.0)
    console.write("shader failed", level="error", source="renderer", timestamp=3.0)
    console.write("other error", level="error", source="physics", timestamp=4.0)

    frame = console.frame(query="render", levels=("warning", "error"))
    assert [entry.message for entry in frame.entries] == ["texture warning", "shader failed"]
    assert frame.warning_count == 1
    assert frame.error_count == 2
    assert frame.total_entries == 4

    source_frame = console.frame(source="renderer", limit=1)
    assert [entry.message for entry in source_frame.entries] == ["shader failed"]


def test_console_validates_filters_and_can_clear() -> None:
    console = EditorConsole()
    with pytest.raises(ValueError, match="unsupported console level"):
        console.write("bad", level="trace")
    with pytest.raises(ValueError, match="source cannot be empty"):
        console.write("bad", source="  ")
    with pytest.raises(ValueError, match="unsupported console level"):
        console.frame(levels=("trace",))
    with pytest.raises(ValueError, match="at least 1"):
        console.frame(limit=0)

    console.write("ok")
    console.clear()
    assert console.entries == ()


def test_console_logging_handler_captures_standard_logging_records() -> None:
    console = EditorConsole()
    logger = logging.getLogger("swirengine.tests.editor")
    handler = console.logging_handler(formatter=logging.Formatter("%(levelname)s:%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    try:
        logger.warning("careful")
    finally:
        logger.removeHandler(handler)

    [entry] = console.entries
    assert entry.level == "warning"
    assert entry.source == "swirengine.tests.editor"
    assert entry.message == "WARNING:careful"
    assert console.logging_handler() is handler


def _record_frame(profiler: Profiler, seconds: float) -> None:
    profiler.begin_frame()
    profiler.record("update", seconds * 0.20)
    profiler.record("physics", seconds * 0.10)
    profiler.record("render", seconds * 0.50)
    profiler.end_frame(seconds)


def test_editor_profiler_derives_window_average_peaks_and_budget_health() -> None:
    profiler = Profiler(history=10)
    for seconds in (0.010, 0.020, 0.030):
        _record_frame(profiler, seconds)

    editor = EditorProfiler(profiler, window=2, target_fps=50.0)
    frame = editor.frame()

    assert frame.sample_count == 2
    assert frame.latest.frame_ms == pytest.approx(30.0)
    assert frame.average.frame_ms == pytest.approx(25.0)
    assert frame.peak_frame_ms == pytest.approx(30.0)
    assert frame.minimum_fps == pytest.approx(1000.0 / 30.0)
    assert frame.frame_budget_ms == pytest.approx(20.0)
    assert frame.over_budget_frames == 1
    assert frame.over_budget_ratio == pytest.approx(0.5)
    assert not frame.frame_budget_ok


def test_editor_profiler_handles_empty_history_and_reconfiguration() -> None:
    profiler = Profiler()
    editor = EditorProfiler(profiler)

    empty = editor.frame()
    assert empty.sample_count == 0
    assert empty.latest.frame_ms == 0.0
    assert empty.over_budget_ratio == 0.0

    editor.configure(window=10, target_fps=120.0)
    assert editor.window == 10
    assert editor.frame_budget_ms == pytest.approx(1000.0 / 120.0)

    with pytest.raises(ValueError, match="at least 1"):
        editor.configure(window=0)
    with pytest.raises(ValueError, match="greater than zero"):
        editor.configure(target_fps=0)
