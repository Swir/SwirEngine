from __future__ import annotations

from dataclasses import dataclass

from swirengine import Scene
from swirengine.editor import SceneInspector
from swirengine.editor_authoring import EditorAuthoringSession
from swirengine.editor_authoring_runtime import EditorAuthoringPlayController
from swirengine.editor_runtime import EditorRuntimeSession
from swirengine.serialization import SceneCodecRegistry, SceneSerializer


@dataclass
class Actor:
    name: str
    x: float = 0.0
    enabled: bool = True

    def update(self, dt: float) -> None:
        self.x += float(dt)


def main() -> None:
    registry = SceneCodecRegistry.default()
    registry.register(Actor)
    serializer = SceneSerializer(registry)

    scene = Scene()
    actor = scene.add(Actor("Player", x=2.0))
    authoring = EditorAuthoringSession(SceneInspector(scene))
    authoring.select(actor)

    play = EditorAuthoringPlayController(
        authoring,
        EditorRuntimeSession(scene, serializer=serializer, fixed_step=0.25),
    )
    runtime = play.play()
    play.update(1.0)
    runtime_actor = runtime.find("Player")
    print(
        "play:",
        f"runtime_x={runtime_actor.x}",
        f"edit_x={actor.x}",
        f"locked={play.authoring_locked}",
    )
    play.pause()
    play.step()
    play.play()
    play.stop()
    print(
        "edit:",
        f"x={actor.x}",
        f"selection={authoring.selection_snapshot.count}",
        f"locked={play.authoring_locked}",
    )


if __name__ == "__main__":
    main()
