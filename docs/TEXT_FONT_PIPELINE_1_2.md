# Text/font pipeline (SwirEngine 1.2)

SwirEngine 1.2 adds a creator-facing text layout layer on top of the existing renderer-native `Text2D` primitive. The public 1.x `Text2D` API remains valid; the new pipeline handles font assets, fallback families, wrapping, alignment and bounded layout caching before materializing normal `Text2D` objects.

## Main pieces

- `FontAsset` — font source plus optional explicit Unicode coverage ranges.
- `FontFamily` — ordered fallback chain.
- `FontRegistry` — named family registry.
- `TextStyle` — family, size, maximum width, alignment and line spacing.
- `TextLayoutEngine` — deterministic wrapping/layout with a bounded LRU cache.
- `TextLayoutDiagnostics` — requests, hits, misses, evictions, entries, measure calls and fallback switches.

## Example

```python
from swirengine.text import (
    FontAsset,
    FontFamily,
    FontRegistry,
    TextAlign,
    TextLayoutEngine,
    TextStyle,
)

fonts = FontRegistry()
fonts.register(
    FontFamily(
        "hud",
        (
            FontAsset("assets/fonts/Inter-Regular.ttf", "latin", ((0x20, 0x024F),)),
            FontAsset("assets/fonts/NotoSansCyrillic-Regular.ttf", "cyrillic", ((0x0400, 0x052F),)),
        ),
    )
)

text = TextLayoutEngine(fonts)
layout = text.layout(
    "Mission update: Привет! Collect all energy cells.",
    TextStyle(family="hud", font_size=24, max_width=420, align=TextAlign.LEFT),
)
scene.add_many(*text.text_objects(layout, -200, 180, screen_space=True, layer=1500))
```

The fallback ranges are explicit on purpose: projects can describe the character coverage of bundled fonts without platform-specific font discovery. If no ranges are supplied, the face is treated as a universal fallback.

## Wrapping and alignment

`max_width` enables greedy word wrapping. Words wider than the available width are split at character boundaries, so long IDs or unbroken strings cannot silently overflow forever. Explicit `\n` paragraph breaks are preserved. `TextAlign.LEFT`, `CENTER` and `RIGHT` position each line inside the requested block width.

## Cache/performance contract

Layout results use a bounded LRU cache keyed by text plus normalized layout style. Repeating an identical layout request returns the existing immutable `TextLayout` and performs no new measurement work. The regression suite issues 1,000 repeated requests after the first layout and requires all 1,000 to be cache hits with an unchanged `measure_calls` counter.

This is a measured reduction in Python-side text measurement/layout work for repeated UI/HUD strings. It is not presented as an end-to-end FPS claim.

## Renderer integration

`TextLayoutEngine.text_objects()` converts the immutable layout into ordinary renderer-native `Text2D` runs. A line may become multiple `Text2D` objects when the selected fallback font changes. This keeps the existing renderer, scene ownership and public `Text2D` behavior compatible with 1.x while allowing richer text authoring.
