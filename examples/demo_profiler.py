from swirengine import Color, Game, Rectangle2D

game = Game("SwirEngine Profiler", 1000, 650)
game.show_debug()

for row in range(8):
    for column in range(12):
        game.add(
            Rectangle2D(
                x=-330 + column * 60,
                y=-210 + row * 60,
                width=42,
                height=42,
                color=Color(0.2 + row * 0.04, 0.4, 0.8, 1.0),
            )
        )

game.run()
