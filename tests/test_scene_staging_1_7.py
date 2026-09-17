from __future__ import annotations

import threading
from dataclasses import dataclass

import pytest

from swirengine.core.scene import Scene
from swirengine.large_world import ChunkContent
from swirengine.prefab import Prefab
from swirengine.scene_staging17 import (
    PreparedScenePlan,
    SceneActivationState,
    SceneActivationStep,
    SceneStager,
    callback_step,
    chunk_content_step,
    entity_step,
    object_factory_step,
    prefab_step,
)


class Thing:
    def __init__(self, name: str) -> None:
        self.name = name


@dataclass
class Health:
    value: int


def _failing_step(step_id: str = "fail") -> SceneActivationStep:
    def apply(_scene: Scene) -> object:
        raise RuntimeError("activation exploded")

    return callback_step(step_id, apply, lambda _scene, _token: None)


def _single_object_plan(request_id: str, name: str | None = None) -> PreparedScenePlan:
    object_name = request_id if name is None else name
    return PreparedScenePlan(
        request_id,
        (object_factory_step("object", lambda _scene: Thing(object_name)),),
    )


def test_preparation_runs_off_owner_thread_and_activation_runs_on_poll_thread() -> None:
    scene = Scene()
    owner_thread = threading.get_ident()
    seen: dict[str, object] = {"apply_threads": []}

    def builder(context) -> PreparedScenePlan:
        seen["builder_thread"] = threading.get_ident()

        def apply(current_scene: Scene) -> object:
            seen["apply_threads"].append(threading.get_ident())  # type: ignore[union-attr]
            obj = Thing("prepared")
            current_scene.add(obj)
            return obj

        def rollback(current_scene: Scene, token: object) -> None:
            current_scene.remove(token)

        return PreparedScenePlan(
            context.request_id,
            (
                callback_step("a", apply, rollback),
                object_factory_step("b", lambda _scene: Thing("second")),
            ),
        )

    with SceneStager(scene, max_workers=1) as stager:
        stager.submit("room", builder)
        outcomes = stager.run_until_idle(max_steps_per_poll=1)

    assert outcomes[0].state is SceneActivationState.SUCCEEDED
    assert seen["builder_thread"] != owner_thread
    assert seen["apply_threads"] == [owner_thread]
    assert [obj.name for obj in scene.objects] == ["prepared", "second"]


def test_poll_hard_bounds_owning_thread_mutation_steps() -> None:
    scene = Scene()

    def builder(context) -> PreparedScenePlan:
        return PreparedScenePlan(
            context.request_id,
            tuple(
                object_factory_step(f"object-{index}", lambda _scene, i=index: Thing(str(i)))
                for index in range(5)
            ),
        )

    with SceneStager(scene, max_workers=1, max_activation_steps_per_poll=5) as stager:
        stager.submit("bounded", builder)
        previous = 0
        while stager.diagnostics().unfinished:
            stager.poll(max_steps=1)
            current = len(scene.objects)
            assert current - previous <= 1
            previous = current

    assert len(scene.objects) == 5


def test_activation_failure_rolls_back_previous_steps_in_reverse_order() -> None:
    scene = Scene()
    events: list[str] = []

    def transactional(name: str) -> SceneActivationStep:
        obj = Thing(name)

        def apply(current_scene: Scene) -> object:
            current_scene.add(obj)
            events.append(f"apply:{name}")
            return obj

        def rollback(current_scene: Scene, token: object) -> None:
            events.append(f"rollback:{name}")
            current_scene.remove(token)

        return callback_step(name, apply, rollback)

    def builder(context) -> PreparedScenePlan:
        return PreparedScenePlan(
            context.request_id,
            (transactional("a"), transactional("b"), _failing_step()),
        )

    with SceneStager(scene, max_workers=1) as stager:
        stager.submit("transaction", builder)
        outcomes = stager.run_until_idle(max_steps_per_poll=1)

    outcome = outcomes[0]
    assert outcome.state is SceneActivationState.FAILED
    assert outcome.applied_steps == 2
    assert outcome.rolled_back_steps == 2
    assert scene.objects == ()
    assert events == ["apply:a", "apply:b", "rollback:b", "rollback:a"]


def test_cancellation_during_activation_uses_bounded_rollback() -> None:
    scene = Scene()

    def builder(context) -> PreparedScenePlan:
        return PreparedScenePlan(
            context.request_id,
            tuple(
                object_factory_step(f"s{index}", lambda _scene, i=index: Thing(str(i)))
                for index in range(4)
            ),
        )

    with SceneStager(scene, max_workers=1) as stager:
        stager.submit("cancel-me", builder)
        while len(scene.objects) < 2:
            stager.poll(max_steps=1)
        assert stager.cancel("cancel-me") is True

        previous = len(scene.objects)
        while stager.diagnostics().unfinished:
            stager.poll(max_steps=1)
            current = len(scene.objects)
            assert previous - current <= 1
            previous = current

        outcome = stager.outcome("cancel-me")

    assert outcome.state is SceneActivationState.CANCELLED
    assert outcome.rolled_back_steps == 2
    assert scene.objects == ()


def test_failed_builder_is_isolated_and_later_request_can_activate() -> None:
    scene = Scene()

    def broken(_context) -> PreparedScenePlan:
        raise ValueError("bad prepared data")

    with SceneStager(scene, max_workers=2) as stager:
        stager.submit("broken", broken)
        stager.submit("healthy", lambda context: _single_object_plan(context.request_id))
        outcomes = stager.run_until_idle(max_steps_per_poll=1)

    assert [outcome.state for outcome in outcomes] == [
        SceneActivationState.FAILED,
        SceneActivationState.SUCCEEDED,
    ]
    assert [obj.name for obj in scene.objects] == ["healthy"]


def test_plan_id_must_match_request_id() -> None:
    scene = Scene()

    with SceneStager(scene, max_workers=1) as stager:
        stager.submit("expected", lambda _context: _single_object_plan("wrong"))
        outcomes = stager.run_until_idle()

    assert outcomes[0].state is SceneActivationState.FAILED
    assert outcomes[0].error_type == "ValueError"
    assert scene.objects == ()


def test_prefab_adapter_rolls_back_graph_on_later_failure() -> None:
    scene = Scene()
    prefab = Prefab(Thing("root"), Thing("child"), name="pair")

    def builder(context) -> PreparedScenePlan:
        return PreparedScenePlan(
            context.request_id,
            (prefab_step("prefab", prefab), _failing_step()),
        )

    with SceneStager(scene, max_workers=1) as stager:
        stager.submit("prefab-room", builder)
        outcome = stager.run_until_idle(max_steps_per_poll=1)[0]

    assert outcome.state is SceneActivationState.FAILED
    assert scene.objects == ()


def test_entity_adapter_rolls_back_ecs_state_on_later_failure() -> None:
    scene = Scene()

    def builder(context) -> PreparedScenePlan:
        return PreparedScenePlan(
            context.request_id,
            (
                entity_step("enemy", (Health(100),), name="enemy", tags=("hostile",)),
                _failing_step(),
            ),
        )

    with SceneStager(scene, max_workers=1) as stager:
        stager.submit("ecs-room", builder)
        outcome = stager.run_until_idle(max_steps_per_poll=1)[0]

    assert outcome.state is SceneActivationState.FAILED
    assert scene.entities == ()


def test_chunk_content_adapter_rolls_back_objects_and_entities() -> None:
    scene = Scene()

    def content_factory(current_scene: Scene) -> ChunkContent:
        entity = current_scene.compose_entity(Health(25), name="crate-ecs")
        return ChunkContent(objects=(Thing("crate"),), entities=(entity,))

    def builder(context) -> PreparedScenePlan:
        return PreparedScenePlan(
            context.request_id,
            (chunk_content_step("chunk", content_factory), _failing_step()),
        )

    with SceneStager(scene, max_workers=1) as stager:
        stager.submit("chunk-room", builder)
        outcome = stager.run_until_idle(max_steps_per_poll=1)[0]

    assert outcome.state is SceneActivationState.FAILED
    assert scene.objects == ()
    assert scene.entities == ()


def test_chunk_content_adapter_rejects_unlisted_new_entities_without_leak() -> None:
    scene = Scene()

    def content_factory(current_scene: Scene) -> ChunkContent:
        current_scene.compose_entity(Health(10), name="forgotten")
        return ChunkContent(objects=(Thing("object"),), entities=())

    def builder(context) -> PreparedScenePlan:
        return PreparedScenePlan(
            context.request_id,
            (chunk_content_step("chunk", content_factory),),
        )

    with SceneStager(scene, max_workers=1) as stager:
        stager.submit("bad-chunk", builder)
        outcome = stager.run_until_idle(max_steps_per_poll=1)[0]

    assert outcome.state is SceneActivationState.FAILED
    assert "not listed" in (outcome.error_message or "")
    assert scene.objects == ()
    assert scene.entities == ()


def test_poll_from_non_owner_thread_is_rejected_before_scene_mutation() -> None:
    scene = Scene()
    errors: list[RuntimeError] = []

    with SceneStager(scene, max_workers=1) as stager:
        stager.submit("owner-only", lambda context: _single_object_plan(context.request_id))

        def wrong_thread() -> None:
            try:
                stager.poll()
            except RuntimeError as exc:
                errors.append(exc)

        thread = threading.Thread(target=wrong_thread)
        thread.start()
        thread.join()
        stager.run_until_idle()

    assert len(errors) == 1
    assert isinstance(errors[0], RuntimeError)
    assert "owning thread" in str(errors[0])
    assert len(scene.objects) == 1


def test_diagnostics_are_payload_free_and_track_transactions() -> None:
    scene = Scene()

    with SceneStager(scene, max_workers=1) as stager:
        stager.submit("diagnostics", lambda context: _single_object_plan(context.request_id))
        stager.run_until_idle()
        portable = dict(stager.diagnostics().portable())

    assert portable["succeeded"] == 1
    assert portable["applied_steps_total"] == 1
    assert all(isinstance(value, int) for value in portable.values())
    assert all("token" not in key and "payload" not in key for key in portable)


def test_forget_releases_request_id_for_reuse() -> None:
    scene = Scene()

    with SceneStager(scene, max_workers=1) as stager:
        stager.submit("reusable", lambda context: _single_object_plan(context.request_id, "one"))
        stager.run_until_idle()
        stager.forget("reusable")
        stager.submit("reusable", lambda context: _single_object_plan(context.request_id, "two"))
        outcome = stager.run_until_idle()[0]

    assert outcome.state is SceneActivationState.SUCCEEDED
    assert [obj.name for obj in scene.objects] == ["one", "two"]


def test_validation_rejects_duplicate_steps_and_request_ids() -> None:
    step = object_factory_step("same", lambda _scene: Thing("x"))
    with pytest.raises(ValueError, match="unique"):
        PreparedScenePlan("duplicate", (step, step))

    scene = Scene()
    with SceneStager(scene, max_workers=1) as stager:
        stager.submit("same-request", lambda context: _single_object_plan(context.request_id))
        with pytest.raises(ValueError, match="duplicate"):
            stager.submit("same-request", lambda context: _single_object_plan(context.request_id))
        stager.run_until_idle()
