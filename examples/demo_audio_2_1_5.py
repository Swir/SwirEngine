from __future__ import annotations

import tempfile
from pathlib import Path

from swirengine.audio15 import AudioEngine2, AudioSnapshot


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="swirengine-audio2-demo-") as directory:
        root = Path(directory)
        for name in ("blip.wav", "alarm.wav", "music.wav"):
            (root / name).write_bytes(f"demo:{name}".encode())

        audio = AudioEngine2.headless(root, max_voices=2)
        ambient = audio.play("blip.wav", priority=10, loop=True, position=(-4.0, 0.0, 2.0))
        action = audio.play("alarm.wav", priority=80, loop=True, position=(3.0, 0.0, 1.0))
        critical = audio.play("alarm.wav", priority=200, protected=True)
        music = audio.music("music.wav", volume=0.6)

        assert ambient is not None
        assert action is not None
        assert critical is not None
        assert not ambient.active
        assert music.active

        focus = AudioSnapshot.from_mapping(
            "focus",
            {
                "sfx": {"volume": 0.35},
                "dialogue": {"volume": 1.0, "muted": False},
            },
            master_volume=0.8,
        )
        audio.apply_snapshot(focus, duration=0.5)
        audio.update(0.25)
        halfway = audio.diagnostics()
        audio.update(0.25)
        settled = audio.diagnostics()

        print("SwirEngine 1.5 Audio 2.0 demo")
        print(f"active SFX voices: {settled.active_voices}/{settled.max_voices}")
        print(f"stolen voices: {settled.stolen_voices}")
        print(f"snapshot halfway: {halfway.transition_snapshot}")
        print(f"snapshot settled: {settled.current_snapshot}")
        print(f"headless events: {settled.backend_events}")
        print(f"state fingerprint: {audio.state_fingerprint()}")

        assert settled.stolen_voices == 1
        assert settled.current_snapshot == "focus"
        assert settled.transition_snapshot is None
        assert settled.backend_events > 0
        audio.shutdown()


if __name__ == "__main__":
    main()
