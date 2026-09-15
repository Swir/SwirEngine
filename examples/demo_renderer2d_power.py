from __future__ import annotations

import math
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

from swirengine import Game


def _make_atlas(path: Path) -> None:
    image = Image.new("RGBA", (64, 64), (20, 24, 34, 255))
    draw = ImageDraw.Draw(image)
    colors = (
        (50, 180, 255, 255),
        (80, 220, 140, 255),
        (245, 190, 70, 255),
        (230, 90, 130, 255),
    )
    for row in range(4):
        for column in range(4):
            color = colors[(row + column) % len(colors)]
            x0, y0 = column * 16, row * 16
            draw.rectangle((x0, y0, x0 + 15, y0 + 15), fill=color)
            draw.rectangle((x0 + 2, y0 + 2, x0 + 13, y0 + 13), outline=(255, 255, 255, 90))
    image.save(path)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="swirengine-2d-demo-") as temporary:
        root = Path(temporary)
        _make_atlas(root / "tiles.png")

        game = Game(
            "SwirEngine 1.3 - 2D Renderer Power Pass",
            1280,
            720,
            mode="2d",
            asset_root=root,
        )
        world = game.tilemap("tiles.png", 192, 192, 16, 16, 4, 4)
        for row in range(world.height):
            for column in range(world.width):
                world.set_tile(column, row, (column + row * 3) % 16)

        game.camera.look_at(640.0, 360.0)
        elapsed = 0.0

        @game.update
        def animate_camera(dt: float) -> None:
            nonlocal elapsed
            elapsed += dt
            game.camera.x = 1536.0 + math.sin(elapsed * 0.55) * 1050.0
            game.camera.y = 1536.0 + math.cos(elapsed * 0.43) * 1050.0

        game.run()


if __name__ == "__main__":
    main()
