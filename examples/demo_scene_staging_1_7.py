from __future__ import annotations

from dataclasses import dataclass

from swirengine.core.scene import Scene
from swirengine.prefab import Prefab
from swirengine.scene_staging17 import (
    PreparedScenePlan,
    SceneStager,
    entity_step,
    object_factory_step,
    prefab_step,
)


class Prop:
    def __init__(self, name: str) -> None:
        self.name = name


@dataclass
class Health:
    value: int


def main() -> None:
    scene = Scene()
    lamp_prefab = Prefab(Prop("lamp"), name="lamp")

    def build_room(context) -> PreparedScenePlan:
        # This function runs on a background worker. It describes work but never receives
        # the live Scene, renderer or window.
        context.raise_if_cancelled()
        return PreparedScenePlan(
            context.request_id,
            (
                object_factory_step("floor", lambda _scene: Prop("floor")),
                prefab_step("lamp", lamp_prefab),
                entity_step(
                    "enemy",
                    (Health(100),),
                    name="guard",
                    tags=("enemy",),
                ),
            ),
            source="creator-demo",
        )

    with SceneStager(
        scene,
        max_workers=2,
        max_activation_steps_per_poll=1,
    ) as stager:
        stager.submit("room-a", build_room, priority=10)
        outcomes = stager.run_until_idle(max_steps_per_poll=1)

        outcome = outcomes[0]
        diagnostics = stager.diagnostics().portable()
        print(
            "Scene staging:",
            outcome.state.value,
            f"objects={len(scene.objects)}",
            f"entities={len(scene.entities)}",
            f"applied={outcome.applied_steps}",
        )
        print("Diagnostics:", dict(diagnostics))


if __name__ == "__main__":
    main()
