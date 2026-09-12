from swirengine import Color, Game, Rectangle2D
from swirengine.prefab import Prefab


game = Game("Prefab Demo", 960, 540)

enemy_prefab = Prefab(
    Rectangle2D(0, 0, 60, 60, Color(0.85, 0.2, 0.25, 1.0), name="body", tags={"enemy"}),
    Rectangle2D(0, 42, 26, 12, Color(1.0, 0.85, 0.2, 1.0), name="marker", tags={"enemy"}),
    name="enemy",
)

for index, x in enumerate((-240.0, -80.0, 80.0, 240.0)):
    game.scene.instantiate(
        enemy_prefab,
        overrides={
            "body": {"x": x},
            "marker": {"x": x},
            0: {"name": f"enemy_{index}"},
        },
    )

game.run()
