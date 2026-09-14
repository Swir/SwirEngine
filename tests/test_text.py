from swirengine.math.types import Color
from swirengine.text import (
    FontAsset,
    FontFamily,
    FontRegistry,
    TextAlign,
    TextLayoutEngine,
    TextStyle,
)


def _measure(text: str, _face: FontAsset, size: int) -> tuple[float, float]:
    return (len(text) * (size / 2), float(size))


def _registry() -> FontRegistry:
    registry = FontRegistry()
    registry.register(
        FontFamily(
            "game",
            (
                FontAsset("latin.ttf", "latin", ((0x20, 0x024F),)),
                FontAsset("cyrillic.ttf", "cyrillic", ((0x0400, 0x052F),)),
            ),
        )
    )
    return registry


def test_font_registry_resolves_explicit_unicode_fallbacks() -> None:
    family = _registry().family("game")

    assert family.resolve("A").name == "latin"
    assert family.resolve("Ж").name == "cyrillic"
    assert family.resolve(" ").name == "latin"


def test_layout_wraps_and_centers_lines() -> None:
    engine = TextLayoutEngine(_registry(), measure=_measure)
    layout = engine.layout(
        "alpha beta gamma",
        TextStyle(family="game", font_size=20, max_width=60, align=TextAlign.CENTER),
    )

    assert [line.text for line in layout.lines] == ["alpha", "beta", "gamma"]
    assert layout.width == 60
    assert layout.lines[0].width == 50
    assert layout.lines[0].x == 5
    assert layout.lines[1].width == 40
    assert layout.lines[1].x == 10


def test_layout_preserves_explicit_newlines_and_breaks_long_words() -> None:
    engine = TextLayoutEngine(_registry(), measure=_measure)
    layout = engine.layout(
        "abcdef\nxy",
        TextStyle(family="game", font_size=20, max_width=30),
    )

    assert [line.text for line in layout.lines] == ["abc", "def", "xy"]


def test_layout_splits_runs_when_fallback_changes() -> None:
    engine = TextLayoutEngine(_registry(), measure=_measure)
    layout = engine.layout("ABЖГ", TextStyle(family="game", font_size=20))

    runs = layout.lines[0].runs
    assert [run.text for run in runs] == ["AB", "ЖГ"]
    assert [run.font.name for run in runs] == ["latin", "cyrillic"]
    assert engine.diagnostics.fallback_switches == 1


def test_repeated_layout_hits_cache_without_new_measure_work() -> None:
    engine = TextLayoutEngine(_registry(), measure=_measure)
    style = TextStyle(family="game", font_size=20, max_width=100)

    first = engine.layout("cached text", style)
    measure_calls = engine.diagnostics.measure_calls
    for _ in range(1000):
        assert engine.layout("cached text", style) is first

    diagnostics = engine.diagnostics
    assert diagnostics.requests == 1001
    assert diagnostics.cache_hits == 1000
    assert diagnostics.cache_misses == 1
    assert diagnostics.measure_calls == measure_calls
    assert diagnostics.entries == 1


def test_lru_cache_is_bounded_and_reports_evictions() -> None:
    engine = TextLayoutEngine(_registry(), cache_limit=8, measure=_measure)

    for index in range(12):
        engine.layout(f"line {index}", TextStyle(family="game"))

    assert engine.diagnostics.entries == 8
    assert engine.diagnostics.evictions == 4


def test_text_objects_materialize_renderer_native_runs() -> None:
    engine = TextLayoutEngine(_registry(), measure=_measure)
    layout = engine.layout("AЖ", TextStyle(family="game", font_size=20))

    objects = engine.text_objects(
        layout,
        100,
        50,
        color=Color(0.2, 0.4, 0.8, 1.0),
        layer=42,
        screen_space=True,
    )

    assert len(objects) == 2
    assert [str(obj.font) for obj in objects] == ["latin.ttf", "cyrillic.ttf"]
    assert all(obj.layer == 42 for obj in objects)
    assert all(obj.screen_space for obj in objects)
    assert objects[0].x < objects[1].x
