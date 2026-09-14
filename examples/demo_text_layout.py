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
        "ui",
        (
            FontAsset(name="latin", ranges=((0x20, 0x024F),)),
            FontAsset(name="cyrillic", ranges=((0x0400, 0x052F),)),
        ),
    )
)

engine = TextLayoutEngine(fonts)
style = TextStyle(
    family="ui",
    font_size=24,
    max_width=360,
    align=TextAlign.CENTER,
    line_spacing=1.15,
)
layout = engine.layout("SwirEngine HUD text wraps cleanly. Привет 1.2!", style)
objects = engine.text_objects(layout, 0, 160, screen_space=True, layer=1400)

print("lines:", [line.text for line in layout.lines])
print("renderer objects:", len(objects))
print("cache before repeat:", engine.diagnostics)
engine.layout("SwirEngine HUD text wraps cleanly. Привет 1.2!", style)
print("cache after repeat:", engine.diagnostics)
