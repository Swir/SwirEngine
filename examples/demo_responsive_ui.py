import swirengine


game = swirengine.Game("SwirEngine Responsive UI", 1280, 720)

status = game.label(
    "Keyboard: arrows/Tab + Enter | Gamepad: D-pad + A",
    0,
    0,
    font_size=18,
    color=swirengine.Color(0.72, 0.86, 1.0, 1.0),
)
progress = game.progress_bar(0, 0, 320, 24, value=0.35)


def on_play(_button):
    progress.value = min(1.0, progress.value + 0.1)
    status.text = f"Play activated — progress {progress.value:.0%}"


def on_reset(_button):
    progress.value = 0.0
    status.text = "Progress reset"


play = game.button("Play / Add 10%", 0, 0, 260, 58, on_click=on_play)
reset = game.button("Reset", 0, 0, 260, 58, on_click=on_reset)

# The controls keep their authored sizes at 1280x720, scale uniformly at other
# resolutions and remain centered automatically. UIManager also handles focus
# navigation and activation; no separate keyboard/gamepad menu code is needed.
game.ui.container(
    status,
    progress,
    play,
    reset,
    spacing=22,
    layout=swirengine.UILayout(
        anchor=swirengine.UIAnchor.CENTER,
        scale_with_viewport=True,
        reference_width=1280,
        reference_height=720,
        min_scale=0.65,
        max_scale=1.75,
    ),
)

game.run()
