from __future__ import annotations

from pathlib import Path

from swirengine.cli import new_project
from swirengine.core.scene import Scene
from swirengine.editor_integrated_session21 import EditorIntegratedProjectSession21
from swirengine.input import InputBinding
from swirengine.physics.rigidbody2d import RigidBody2D
from swirengine.shipping19 import ProjectShippingDefaults


class RecordingAudioBackend:
    def __init__(self) -> None:
        self.play_calls: list[tuple[Path, float, bool, bool]] = []
        self.closed = False

    def play(self, path: Path, *, volume: float, loop: bool, music: bool) -> object:
        self.play_calls.append((path, volume, loop, music))
        return object()

    def stop(self, token: object) -> None:
        return None

    def set_volume(self, token: object, volume: float) -> None:
        return None

    def stop_all(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


def test_milestone_8_complete_gameplay_tooling_workflow(tmp_path: Path, monkeypatch) -> None:
    """Exercise all eight Milestone 8 creator areas through one project session."""
    monkeypatch.chdir(tmp_path)
    root = new_project("Milestone8Gate", "2d")
    session = EditorIntegratedProjectSession21.open(root)

    # Input/rebinding + settings use the shipping project defaults contract.
    session.gameplay.bind_key("jump", "space")
    session.gameplay.update_display(width=1600, height=900, vsync=False)
    session.gameplay.update_accessibility(subtitles=True, text_scale=1.25)

    # Animation preview samples the same runtime AnimationClip implementation.
    animation = session.animation.new_clip("Player Run", duration=1.0, loop=True)
    assert animation.clip is not None
    session.animation.add_track("transform.position", initial_value=[0.0, 0.0])
    session.animation.set_keyframe("transform.position", 1.0, [10.0, 4.0])
    assert session.animation.sample(0.5).values["transform.position"] == [5.0, 2.0]

    # Physics creates a real runtime rigid body from authored collision data.
    session.physics.create_body(
        "Player",
        dimension="2d",
        shape="box",
        size=(32.0, 48.0),
        mass=2.0,
        tag="player",
    )
    physics_body = session.physics.build_runtime("Player", position=(10.0, 20.0))
    assert isinstance(physics_body, RigidBody2D)

    # Navigation/AI builds the shipping graph and finds a creator-authored path.
    session.navigation.create_node("spawn", (0.0, 0.0, 0.0))
    session.navigation.create_node("goal", (4.0, 0.0, 0.0))
    session.navigation.create_edge("spawn-goal", "spawn", "goal", area="road")
    session.navigation.create_agent("enemy", (0.0, 0.0, 0.0), max_speed=2.0)
    navigation_runtime = session.navigation.build_runtime()
    path_result = navigation_runtime.set_target("enemy", (4.0, 0.0, 0.0))
    assert path_result.path is not None
    assert path_result.path.node_ids == ("spawn", "goal")

    # Audio preview is routed through the shipping AudioEngine contract.
    audio_dir = root / "assets" / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    (audio_dir / "laser.wav").write_bytes(b"swir-m8-audio")
    session.audio.create_bus("ui", volume=0.5)
    session.audio.create_cue("laser", "audio/laser.wav", bus="ui", volume=0.8)
    audio_backend = RecordingAudioBackend()
    audio_engine, audio_handle = session.audio.preview_cue("laser", backend=audio_backend)
    assert audio_handle.active is True
    assert audio_handle.bus == "ui"
    assert audio_backend.play_calls
    audio_engine.shutdown()
    assert audio_backend.closed is True

    # UI/HUD authoring instantiates the production UIManager into a real Scene.
    session.ui_hud.create_element("title", "label", text="SWIR", x=120, y=60)
    session.ui_hud.create_element(
        "health",
        "progress",
        x=180,
        y=110,
        width=280,
        height=20,
        value=0.75,
    )
    ui_scene = Scene()
    ui_runtime = session.ui_hud.build_runtime(ui_scene)
    assert len(ui_runtime.controls) == 2
    assert len(ui_scene.objects) >= 2

    # Save/profile policy proves a real async save/load round trip.
    session.save_profile.update_identity(default_profile="campaign", version=2)
    session.save_profile.update_policy(autosave_keep=4, max_manual_slots=20)
    session.save_profile.replace_defaults({"level": 1, "checkpoint": "spawn"})
    session.save_profile.validate_runtime(tmp_path / "user-data")

    assert session.summary().dirty is True
    session.save()
    assert session.summary().dirty is False

    # Reopen the same project and prove every authored domain persisted.
    reopened = EditorIntegratedProjectSession21.open(root)
    defaults = ProjectShippingDefaults.load(root)
    assert defaults.actions.bindings("jump") == (InputBinding("key", "space"),)
    assert defaults.settings.display.width == 1600
    assert defaults.settings.display.height == 900
    assert defaults.settings.accessibility.subtitles is True

    reopened.animation.load("assets/animations/player-run.swiranim.json")
    assert reopened.animation.sample(0.5).values["transform.position"] == [5.0, 2.0]
    assert {body.name for body in reopened.physics.snapshot().bodies} == {"Player"}
    assert {node.name for node in reopened.navigation.snapshot().nodes} == {"spawn", "goal"}
    assert {cue.name for cue in reopened.audio.snapshot().cues} == {"laser"}
    assert {element.name for element in reopened.ui_hud.snapshot().elements} == {
        "health",
        "title",
    }
    assert reopened.save_profile.config.default_profile == "campaign"
    assert reopened.save_profile.config.version == 2
    assert reopened.save_profile.config.policy.autosave_keep == 4
    assert reopened.summary().dirty is False
