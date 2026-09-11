from swirengine import Color, Game

game = Game("SwirEngine UI", 960, 540)
game.panel(0, 0, 420, 260)
game.label("SwirEngine UI", 0, 90, font_size=32)
progress = game.progress_bar(0, -20, 300, 24, value=0.35)
status = game.label("Ready", 0, 35, font_size=20, color=Color(0.7, 0.85, 1.0, 1.0))


def on_click(_button):
    progress.value = min(1.0, progress.value + 0.1)
    status.text = f"Progress: {progress.value:.0%}"


game.button("Add 10%", 0, -85, 180, 52, on_click=on_click)
game.run()
