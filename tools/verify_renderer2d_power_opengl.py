from __future__ import annotations

import tempfile
from pathlib import Path

from PIL import Image

from swirengine import Game


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="swirengine-2d-power-") as temporary:
        root = Path(temporary)
        atlas = root / "tiles.png"
        image = Image.new("RGBA", (64, 64), (255, 255, 255, 255))
        image.save(atlas)

        game = Game(
            "SwirEngine 2D power-pass smoke",
            640,
            360,
            mode="2d",
            vsync=False,
            target_fps=240,
            asset_root=root,
        )
        tilemap = game.tilemap("tiles.png", 96, 96, 16, 16, 4, 4).fill(1)
        game.camera.look_at(320.0, 180.0)

        frames = 0

        @game.update
        def move_camera_and_stop(dt: float) -> None:
            nonlocal frames
            del dt
            frames += 1
            game.camera.x += 4.0
            if frames >= 5:
                game.stop()

        game.run()
        assert frames >= 5
        assert tilemap.diagnostics.visibility_queries >= 5
        assert tilemap.diagnostics.last_visibility_candidates < tilemap.tile_count // 4
        print(
            "2D power OpenGL smoke rendered five frames; "
            f"last_candidates={tilemap.diagnostics.last_visibility_candidates}, "
            f"total_tiles={tilemap.tile_count}."
        )


if __name__ == "__main__":
    main()
