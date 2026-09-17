from __future__ import annotations

import time

from swirengine.core.scene import Scene
from swirengine.scene_staging17 import PreparedScenePlan, SceneStager, callback_step

PLAN_COUNT = 512
STEPS_PER_PLAN = 4
BUDGET_SECONDS = 5.0


def main() -> None:
    scene = Scene()

    def builder(context) -> PreparedScenePlan:
        steps = tuple(
            callback_step(
                f"step-{index}",
                lambda _scene: None,
                lambda _scene, _token: None,
            )
            for index in range(STEPS_PER_PLAN)
        )
        return PreparedScenePlan(context.request_id, steps)

    started = time.perf_counter()
    with SceneStager(
        scene,
        max_workers=4,
        max_pending_preparations=PLAN_COUNT,
        max_requests=PLAN_COUNT,
        max_activation_steps_per_poll=32,
    ) as stager:
        for index in range(PLAN_COUNT):
            stager.submit(f"plan-{index:04d}", builder)
        outcomes = stager.run_until_idle(max_steps_per_poll=32, timeout=BUDGET_SECONDS)
    elapsed = time.perf_counter() - started

    expected_steps = PLAN_COUNT * STEPS_PER_PLAN
    assert len(outcomes) == PLAN_COUNT
    assert all(outcome.state.value == "succeeded" for outcome in outcomes)
    assert sum(outcome.applied_steps for outcome in outcomes) == expected_steps
    assert elapsed < BUDGET_SECONDS, (
        f"scene staging workload exceeded {BUDGET_SECONDS:.1f}s budget: {elapsed:.4f}s"
    )
    print(
        "Scene staging workload: "
        f"{PLAN_COUNT} plans / {expected_steps} activation steps in {elapsed:.4f}s; "
        f"budget {BUDGET_SECONDS:.1f}s"
    )


if __name__ == "__main__":
    main()
