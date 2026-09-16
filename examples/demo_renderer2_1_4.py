from __future__ import annotations

from swirengine import Color, Cube3D, Game, Vec3


def main() -> None:
    game = Game("SwirEngine 1.4 Renderer 2.0", mode="3d", width=1280, height=720)
    game.configure_renderer2(
        shadow_cascades=4,
        shadow_resolution=2048,
        shadow_distance=120.0,
        ssao=True,
        ssao_samples=16,
        bloom=True,
        bloom_levels=5,
        decals=True,
        max_decals=128,
        hdr=True,
    )
    game.configure_postprocess(enabled=True, tone_mapping="aces", exposure=1.05, fxaa=True)

    game.directional_light(
        direction=Vec3(-0.6, -1.0, -0.35),
        intensity=1.8,
        color=Color(1.0, 0.94, 0.84, 1.0),
    )

    for row in range(4):
        for column in range(7):
            x = float(column - 3) * 2.2
            z = -3.0 - float(row) * 3.0
            height = 0.6 + float((row + column) % 4) * 0.45
            game.add(
                Cube3D(
                    position=Vec3(x, height * 0.5 - 0.5, z),
                    scale=Vec3(1.1, height, 1.1),
                    color=Color(
                        0.12 + 0.06 * row,
                        0.32 + 0.05 * column,
                        0.72,
                        1.0,
                    ),
                )
            )

    game.add(
        Cube3D(
            position=Vec3(0.0, -1.15, -7.5),
            scale=Vec3(20.0, 0.25, 20.0),
            color=Color(0.08, 0.09, 0.12, 1.0),
        )
    )
    game.decal(
        position=Vec3(0.0, -1.0, -6.0),
        size=Vec3(5.0, 0.35, 5.0),
        color=Color(0.05, 0.75, 1.0, 0.55),
        opacity=0.85,
    )

    game.run()


if __name__ == "__main__":
    main()
