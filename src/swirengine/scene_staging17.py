from __future__ import annotations

import copy
import math
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, TypeAlias

from .core.scene import Scene, SceneMount
from .jobs17 import JobContext, JobOutcome, JobScheduler, JobState
from .large_world import ChunkContent
from .prefab import Prefab, PrefabInstance, PrefabOverrides


def _identifier(value: str, *, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    normalized = value.strip()
    if not normalized or len(normalized) > 96:
        raise ValueError(f"{label} must contain 1 to 96 non-whitespace characters")
    return normalized


def _positive_int(value: int, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if value < 1:
        raise ValueError(f"{label} must be >= 1")
    return value


class SceneActivationState(str, Enum):
    PREPARING = "preparing"
    READY = "ready"
    ACTIVATING = "activating"
    ROLLING_BACK = "rolling_back"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


_TERMINAL_STATES = {
    SceneActivationState.SUCCEEDED,
    SceneActivationState.FAILED,
    SceneActivationState.CANCELLED,
}


@dataclass(frozen=True, slots=True)
class SceneBuildContext:
    """Background-only scene preparation context.

    It intentionally contains no live :class:`Scene` reference. Builders can prepare immutable
    descriptors and CPU-side data, then return a :class:`PreparedScenePlan` whose mutation
    callbacks are executed later by :meth:`SceneStager.poll` on the owning thread.
    """

    request_id: str
    sequence: int
    job: JobContext

    @property
    def cancelled(self) -> bool:
        return self.job.cancelled

    def raise_if_cancelled(self) -> None:
        self.job.raise_if_cancelled()


SceneApply: TypeAlias = Callable[[Scene], object]
SceneRollback: TypeAlias = Callable[[Scene, object], None]


@dataclass(frozen=True, slots=True)
class SceneActivationStep:
    """One owning-thread scene mutation plus its compensating rollback."""

    step_id: str
    apply: SceneApply
    rollback: SceneRollback
    label: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "step_id", _identifier(self.step_id, label="step_id"))
        if not callable(self.apply):
            raise TypeError("scene activation apply callback must be callable")
        if not callable(self.rollback):
            raise TypeError("scene activation rollback callback must be callable")
        object.__setattr__(self, "label", str(self.label))


@dataclass(frozen=True, slots=True)
class PreparedScenePlan:
    """Immutable descriptor for bounded scene activation.

    A plan stores callbacks, not a live Scene. Custom apply callbacks should either be atomic or
    clean up their own partial mutation before raising. The built-in adapters in this module do
    that automatically.
    """

    plan_id: str
    steps: tuple[SceneActivationStep, ...]
    source: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "plan_id", _identifier(self.plan_id, label="plan_id"))
        steps = tuple(self.steps)
        if not steps:
            raise ValueError("prepared scene plan requires at least one activation step")
        if any(not isinstance(step, SceneActivationStep) for step in steps):
            raise TypeError("prepared scene plan steps must be SceneActivationStep values")
        step_ids = tuple(step.step_id for step in steps)
        if len(set(step_ids)) != len(step_ids):
            raise ValueError("prepared scene plan step ids must be unique")
        object.__setattr__(self, "steps", steps)
        object.__setattr__(self, "source", str(self.source))

    @property
    def size(self) -> int:
        return len(self.steps)

    def portable(self) -> Mapping[str, object]:
        return MappingProxyType(
            {
                "plan_id": self.plan_id,
                "source": self.source,
                "steps": tuple(step.step_id for step in self.steps),
            }
        )


ScenePlanBuilder: TypeAlias = Callable[[SceneBuildContext], PreparedScenePlan]


@dataclass(frozen=True, slots=True)
class SceneActivationOutcome:
    request_id: str
    sequence: int
    state: SceneActivationState
    plan_id: str | None
    total_steps: int
    applied_steps: int
    rolled_back_steps: int
    error_type: str | None = None
    error_message: str | None = None
    rollback_errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SceneStagingDiagnostics:
    max_requests: int
    max_activation_steps_per_poll: int
    preparing: int
    ready: int
    activating: int
    rolling_back: int
    succeeded: int
    failed: int
    cancelled: int
    submitted_total: int
    rejected_total: int
    applied_steps_total: int
    rolled_back_steps_total: int
    activation_failures_total: int
    rollback_failures_total: int
    cancellation_requests_total: int

    @property
    def unfinished(self) -> int:
        return self.preparing + self.ready + self.activating + self.rolling_back

    def portable(self) -> Mapping[str, int]:
        return MappingProxyType(
            {
                "max_requests": self.max_requests,
                "max_activation_steps_per_poll": self.max_activation_steps_per_poll,
                "preparing": self.preparing,
                "ready": self.ready,
                "activating": self.activating,
                "rolling_back": self.rolling_back,
                "succeeded": self.succeeded,
                "failed": self.failed,
                "cancelled": self.cancelled,
                "unfinished": self.unfinished,
                "submitted_total": self.submitted_total,
                "rejected_total": self.rejected_total,
                "applied_steps_total": self.applied_steps_total,
                "rolled_back_steps_total": self.rolled_back_steps_total,
                "activation_failures_total": self.activation_failures_total,
                "rollback_failures_total": self.rollback_failures_total,
                "cancellation_requests_total": self.cancellation_requests_total,
            }
        )


@dataclass(slots=True)
class _AppliedStep:
    step: SceneActivationStep
    token: object


@dataclass(slots=True)
class _Request:
    request_id: str
    sequence: int
    priority: int
    prep_job_id: str
    state: SceneActivationState = SceneActivationState.PREPARING
    plan: PreparedScenePlan | None = None
    next_step: int = 0
    applied: list[_AppliedStep] = field(default_factory=list)
    rollback_index: int = -1
    rolled_back_steps: int = 0
    error_type: str | None = None
    error_message: str | None = None
    rollback_errors: list[str] = field(default_factory=list)
    cancelled: bool = False


class SceneStager:
    """Background scene preparation with bounded owning-thread activation and rollback.

    Preparation builders run through :class:`JobScheduler`; live Scene mutation happens only in
    :meth:`poll`, which is owner-thread checked and independently bounded by a step budget.
    Requests activate in immutable submission order, making activation deterministic even when
    background preparation completes out of order.
    """

    def __init__(
        self,
        scene: Scene,
        *,
        max_workers: int = 2,
        max_pending_preparations: int = 64,
        max_requests: int = 256,
        max_activation_steps_per_poll: int = 8,
    ) -> None:
        if not isinstance(scene, Scene):
            raise TypeError("scene must be a Scene")
        self.scene = scene
        self.max_requests = _positive_int(max_requests, label="max_requests")
        self.max_activation_steps_per_poll = _positive_int(
            max_activation_steps_per_poll,
            label="max_activation_steps_per_poll",
        )
        self._scheduler = JobScheduler(
            max_workers=max_workers,
            max_pending=max_pending_preparations,
            thread_name_prefix="swir-scene-build",
        )
        self._owner_thread = threading.get_ident()
        self._requests: dict[str, _Request] = {}
        self._job_to_request: dict[str, str] = {}
        self._next_sequence = 1
        self._closed = False
        self._submitted_total = 0
        self._rejected_total = 0
        self._applied_steps_total = 0
        self._rolled_back_steps_total = 0
        self._activation_failures_total = 0
        self._rollback_failures_total = 0
        self._cancellation_requests_total = 0

    def _require_owner_thread(self) -> None:
        if threading.get_ident() != self._owner_thread:
            raise RuntimeError("scene staging activation must run on the owning thread")

    def submit(
        self,
        request_id: str,
        builder: ScenePlanBuilder,
        *,
        priority: int = 0,
    ) -> int:
        normalized_id = _identifier(request_id, label="request_id")
        if not callable(builder):
            raise TypeError("scene plan builder must be callable")
        if isinstance(priority, bool) or not isinstance(priority, int):
            raise TypeError("priority must be an integer")
        if self._closed:
            self._rejected_total += 1
            raise RuntimeError("scene stager is closed")
        if normalized_id in self._requests:
            self._rejected_total += 1
            raise ValueError(f"duplicate scene staging request: {normalized_id}")
        if len(self._requests) >= self.max_requests:
            self._rejected_total += 1
            raise RuntimeError("scene staging request retention budget reached")

        sequence = self._next_sequence
        prep_job_id = f"scene-build-{sequence}"
        context_sequence = sequence

        def prepare(job: JobContext) -> PreparedScenePlan:
            context = SceneBuildContext(
                request_id=normalized_id,
                sequence=context_sequence,
                job=job,
            )
            context.raise_if_cancelled()
            plan = builder(context)
            context.raise_if_cancelled()
            if not isinstance(plan, PreparedScenePlan):
                raise TypeError("scene plan builder must return PreparedScenePlan")
            if plan.plan_id != normalized_id:
                raise ValueError(
                    f"prepared plan id {plan.plan_id!r} must match request id {normalized_id!r}"
                )
            return plan

        try:
            self._scheduler.submit(prep_job_id, prepare, priority=priority)
        except Exception:
            self._rejected_total += 1
            raise

        self._requests[normalized_id] = _Request(
            request_id=normalized_id,
            sequence=sequence,
            priority=priority,
            prep_job_id=prep_job_id,
        )
        self._job_to_request[prep_job_id] = normalized_id
        self._next_sequence += 1
        self._submitted_total += 1
        return sequence

    def _accept_preparation(self, outcome: JobOutcome[Any]) -> None:
        request_id = self._job_to_request.get(outcome.job_id)
        if request_id is None:
            return
        request = self._requests.get(request_id)
        if request is None or request.state is not SceneActivationState.PREPARING:
            return

        if outcome.state is JobState.SUCCEEDED:
            plan = outcome.value
            if not isinstance(plan, PreparedScenePlan):
                request.state = SceneActivationState.FAILED
                request.error_type = "TypeError"
                request.error_message = "scene preparation produced an invalid plan"
                return
            request.plan = plan
            request.state = SceneActivationState.READY
            return

        if outcome.state is JobState.CANCELLED:
            request.cancelled = True
            request.state = SceneActivationState.CANCELLED
            request.error_type = outcome.error_type
            request.error_message = outcome.error_message
            return

        request.state = SceneActivationState.FAILED
        request.error_type = outcome.error_type or outcome.state.value
        request.error_message = outcome.error_message or "scene preparation did not succeed"

    def _begin_rollback(self, request: _Request, *, cancelled: bool) -> None:
        request.cancelled = request.cancelled or cancelled
        if not request.applied:
            request.state = (
                SceneActivationState.CANCELLED
                if request.cancelled and request.error_type is None
                else SceneActivationState.FAILED
            )
            return
        request.rollback_index = len(request.applied) - 1
        request.state = SceneActivationState.ROLLING_BACK

    def _activate_one(self, request: _Request) -> None:
        plan = request.plan
        if plan is None:
            request.state = SceneActivationState.FAILED
            request.error_type = "RuntimeError"
            request.error_message = "prepared plan is missing"
            return
        if request.cancelled:
            self._begin_rollback(request, cancelled=True)
            return
        if request.next_step >= plan.size:
            request.state = SceneActivationState.SUCCEEDED
            return

        request.state = SceneActivationState.ACTIVATING
        step = plan.steps[request.next_step]
        try:
            token = step.apply(self.scene)
        except Exception as exc:
            request.error_type = type(exc).__name__
            request.error_message = str(exc)
            self._activation_failures_total += 1
            self._begin_rollback(request, cancelled=False)
            return

        request.applied.append(_AppliedStep(step=step, token=token))
        request.next_step += 1
        self._applied_steps_total += 1
        if request.next_step >= plan.size:
            request.state = SceneActivationState.SUCCEEDED

    def _rollback_one(self, request: _Request) -> None:
        if request.rollback_index < 0:
            if request.rollback_errors:
                request.error_type = request.error_type or "RollbackError"
                details = "; ".join(request.rollback_errors)
                request.error_message = (
                    f"{request.error_message}; rollback errors: {details}"
                    if request.error_message
                    else f"rollback errors: {details}"
                )
                request.state = SceneActivationState.FAILED
            elif request.cancelled and request.error_type is None:
                request.state = SceneActivationState.CANCELLED
            else:
                request.state = SceneActivationState.FAILED
            return

        applied = request.applied[request.rollback_index]
        try:
            applied.step.rollback(self.scene, applied.token)
        except Exception as exc:
            message = f"{applied.step.step_id}: {type(exc).__name__}: {exc}"
            request.rollback_errors.append(message)
            self._rollback_failures_total += 1
        finally:
            request.rollback_index -= 1
            request.rolled_back_steps += 1
            self._rolled_back_steps_total += 1

        if request.rollback_index < 0:
            self._rollback_one(request)

    def poll(
        self,
        *,
        max_steps: int | None = None,
        max_preparations: int = 32,
    ) -> tuple[SceneActivationOutcome, ...]:
        self._require_owner_thread()
        if max_steps is None:
            step_budget = self.max_activation_steps_per_poll
        else:
            step_budget = _positive_int(max_steps, label="max_steps")
        prep_budget = _positive_int(max_preparations, label="max_preparations")

        before_terminal = {
            request_id
            for request_id, request in self._requests.items()
            if request.state in _TERMINAL_STATES
        }

        for outcome in self._scheduler.drain_completed(max_items=prep_budget):
            self._accept_preparation(outcome)

        mutations = 0
        while mutations < step_budget:
            pending = tuple(
                request
                for request in sorted(self._requests.values(), key=lambda item: item.sequence)
                if request.state not in _TERMINAL_STATES
            )
            if not pending:
                break
            request = pending[0]
            if request.state is SceneActivationState.PREPARING:
                break
            if request.state is SceneActivationState.READY:
                request.state = SceneActivationState.ACTIVATING
            if request.state is SceneActivationState.ACTIVATING:
                previous_applied = len(request.applied)
                previous_state = request.state
                self._activate_one(request)
                if len(request.applied) != previous_applied or (
                    previous_state is SceneActivationState.ACTIVATING
                    and request.state is SceneActivationState.ROLLING_BACK
                ):
                    mutations += 1
                elif request.state in _TERMINAL_STATES:
                    continue
                else:
                    mutations += 1
                continue
            if request.state is SceneActivationState.ROLLING_BACK:
                self._rollback_one(request)
                mutations += 1
                continue
            break

        completed_now = tuple(
            self._outcome(request)
            for request_id, request in sorted(
                self._requests.items(), key=lambda item: item[1].sequence
            )
            if request_id not in before_terminal and request.state in _TERMINAL_STATES
        )
        return completed_now

    def cancel(self, request_id: str) -> bool:
        normalized_id = _identifier(request_id, label="request_id")
        request = self._requests.get(normalized_id)
        if request is None:
            raise KeyError(normalized_id)
        if request.state in _TERMINAL_STATES:
            return False
        self._cancellation_requests_total += 1
        request.cancelled = True

        if request.state is SceneActivationState.PREPARING:
            self._scheduler.cancel(request.prep_job_id)
        elif request.state is SceneActivationState.READY:
            request.state = SceneActivationState.CANCELLED
        elif request.state is SceneActivationState.ACTIVATING:
            self._begin_rollback(request, cancelled=True)
        return True

    def state(self, request_id: str) -> SceneActivationState:
        normalized_id = _identifier(request_id, label="request_id")
        return self._requests[normalized_id].state

    def _outcome(self, request: _Request) -> SceneActivationOutcome:
        plan = request.plan
        return SceneActivationOutcome(
            request_id=request.request_id,
            sequence=request.sequence,
            state=request.state,
            plan_id=None if plan is None else plan.plan_id,
            total_steps=0 if plan is None else plan.size,
            applied_steps=len(request.applied),
            rolled_back_steps=request.rolled_back_steps,
            error_type=request.error_type,
            error_message=request.error_message,
            rollback_errors=tuple(request.rollback_errors),
        )

    def outcome(self, request_id: str) -> SceneActivationOutcome:
        normalized_id = _identifier(request_id, label="request_id")
        request = self._requests[normalized_id]
        if request.state not in _TERMINAL_STATES:
            raise RuntimeError(f"scene staging request {normalized_id!r} is not complete")
        return self._outcome(request)

    def forget(self, request_id: str) -> None:
        self._require_owner_thread()
        normalized_id = _identifier(request_id, label="request_id")
        request = self._requests[normalized_id]
        if request.state not in _TERMINAL_STATES:
            raise RuntimeError("cannot forget an unfinished scene staging request")
        self._scheduler.forget(request.prep_job_id)
        del self._job_to_request[request.prep_job_id]
        del self._requests[normalized_id]

    def diagnostics(self) -> SceneStagingDiagnostics:
        counts = {state: 0 for state in SceneActivationState}
        for request in self._requests.values():
            counts[request.state] += 1
        return SceneStagingDiagnostics(
            max_requests=self.max_requests,
            max_activation_steps_per_poll=self.max_activation_steps_per_poll,
            preparing=counts[SceneActivationState.PREPARING],
            ready=counts[SceneActivationState.READY],
            activating=counts[SceneActivationState.ACTIVATING],
            rolling_back=counts[SceneActivationState.ROLLING_BACK],
            succeeded=counts[SceneActivationState.SUCCEEDED],
            failed=counts[SceneActivationState.FAILED],
            cancelled=counts[SceneActivationState.CANCELLED],
            submitted_total=self._submitted_total,
            rejected_total=self._rejected_total,
            applied_steps_total=self._applied_steps_total,
            rolled_back_steps_total=self._rolled_back_steps_total,
            activation_failures_total=self._activation_failures_total,
            rollback_failures_total=self._rollback_failures_total,
            cancellation_requests_total=self._cancellation_requests_total,
        )

    def run_until_idle(
        self,
        *,
        max_steps_per_poll: int | None = None,
        timeout: float = 10.0,
    ) -> tuple[SceneActivationOutcome, ...]:
        self._require_owner_thread()
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise TypeError("timeout must be a finite non-negative number")
        timeout_value = float(timeout)
        if not math.isfinite(timeout_value) or timeout_value < 0.0:
            raise ValueError("timeout must be a finite non-negative number")
        deadline = time.monotonic() + timeout_value

        while True:
            self.poll(max_steps=max_steps_per_poll)
            if self.diagnostics().unfinished == 0:
                return tuple(
                    self._outcome(request)
                    for request in sorted(
                        self._requests.values(), key=lambda item: item.sequence
                    )
                    if request.state in _TERMINAL_STATES
                )
            if time.monotonic() >= deadline:
                raise TimeoutError("scene staging requests did not become idle before timeout")
            time.sleep(0.0005)

    def shutdown(self, *, wait: bool = True, cancel_pending: bool = False) -> None:
        self._require_owner_thread()
        if not isinstance(wait, bool) or not isinstance(cancel_pending, bool):
            raise TypeError("wait and cancel_pending must be bool values")
        if self._closed:
            return
        self._closed = True

        if cancel_pending:
            for request in tuple(self._requests.values()):
                if request.state not in _TERMINAL_STATES:
                    self.cancel(request.request_id)
            if wait:
                self.run_until_idle(timeout=10.0)

        self._scheduler.shutdown(wait=wait, cancel_pending=cancel_pending)

    def __enter__(self) -> SceneStager:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.shutdown()


def callback_step(
    step_id: str,
    apply: SceneApply,
    rollback: SceneRollback,
    *,
    label: str = "",
) -> SceneActivationStep:
    """Create a custom transactional activation step.

    Custom ``apply`` callbacks should be atomic or undo their own partial mutation before raising,
    because a rollback token only exists after ``apply`` returns successfully.
    """

    return SceneActivationStep(step_id=step_id, apply=apply, rollback=rollback, label=label)


ObjectFactory: TypeAlias = Callable[[Scene], object | Sequence[object]]


def object_factory_step(
    step_id: str,
    factory: ObjectFactory,
    *,
    label: str = "",
) -> SceneActivationStep:
    """Create scene objects on the owning thread and remove them transactionally."""

    if not callable(factory):
        raise TypeError("object factory must be callable")

    def apply(scene: Scene) -> object:
        produced = factory(scene)
        objects = (
            tuple(produced)
            if isinstance(produced, Sequence) and not isinstance(produced, (str, bytes))
            else (produced,)
        )
        if not objects:
            raise ValueError("object factory must produce at least one object")
        try:
            for obj in objects:
                scene.add(obj)
        except Exception:
            for obj in reversed(objects):
                scene.remove(obj)
            raise
        return objects

    def rollback(scene: Scene, token: object) -> None:
        objects = tuple(token)  # type: ignore[arg-type]
        for obj in reversed(objects):
            scene.remove(obj)

    return SceneActivationStep(step_id=step_id, apply=apply, rollback=rollback, label=label)


def prefab_step(
    step_id: str,
    prefab: Prefab,
    *,
    overrides: PrefabOverrides | None = None,
    label: str = "",
) -> SceneActivationStep:
    """Instantiate an existing stable Prefab through a transactional activation step."""

    if not isinstance(prefab, Prefab):
        raise TypeError("prefab must be a Prefab")
    frozen_overrides = None if overrides is None else copy.deepcopy(dict(overrides))

    def apply(scene: Scene) -> object:
        instance = prefab.instantiate(None, overrides=frozen_overrides)
        try:
            for obj in instance.objects:
                scene.add(obj)
        except Exception:
            for obj in reversed(instance.objects):
                scene.remove(obj)
            raise
        return instance

    def rollback(scene: Scene, token: object) -> None:
        if not isinstance(token, PrefabInstance):
            raise TypeError("invalid prefab activation token")
        for obj in reversed(token.objects):
            scene.remove(obj)

    return SceneActivationStep(step_id=step_id, apply=apply, rollback=rollback, label=label)


def entity_step(
    step_id: str,
    components: Sequence[object] = (),
    *,
    name: str = "",
    enabled: bool = True,
    tags: Sequence[str] = (),
    label: str = "",
) -> SceneActivationStep:
    """Compose one ECS entity on activation from background-safe copied component data."""

    component_templates = copy.deepcopy(tuple(components))
    entity_name = str(name)
    entity_tags = tuple(str(tag) for tag in tags)
    entity_enabled = bool(enabled)

    def apply(scene: Scene) -> object:
        before_ids = {entity.id for entity in scene.entities}
        try:
            return scene.compose_entity(
                *copy.deepcopy(component_templates),
                name=entity_name,
                enabled=entity_enabled,
                tags=entity_tags,
            )
        except Exception:
            for entity in tuple(scene.entities):
                if entity.id not in before_ids:
                    scene.ecs.destroy(entity)
            raise

    def rollback(scene: Scene, token: object) -> None:
        destroy = getattr(token, "destroy", None)
        if callable(destroy):
            destroy()
            return
        raise TypeError("invalid ECS activation token")

    return SceneActivationStep(step_id=step_id, apply=apply, rollback=rollback, label=label)


ChunkContentFactory: TypeAlias = Callable[[Scene], ChunkContent]


def chunk_content_step(
    step_id: str,
    factory: ChunkContentFactory,
    *,
    label: str = "",
) -> SceneActivationStep:
    """Mount stable ``ChunkContent`` transactionally without changing streaming APIs.

    The factory runs on the owning thread. Any ECS entities it creates must be listed in the
    returned ``ChunkContent.entities`` tuple; unlisted newly-created entities are rejected and
    cleaned so a failed activation cannot strand scene-owned ECS state.
    """

    if not callable(factory):
        raise TypeError("chunk content factory must be callable")

    def apply(scene: Scene) -> object:
        before_ids = {entity.id for entity in scene.entities}
        content: ChunkContent | None = None
        try:
            content = factory(scene)
            if not isinstance(content, ChunkContent):
                raise TypeError("chunk content factory must return ChunkContent")
            listed_ids = {entity.id for entity in content.entities}
            new_entities = tuple(
                entity for entity in scene.entities if entity.id not in before_ids
            )
            unlisted = tuple(entity for entity in new_entities if entity.id not in listed_ids)
            if unlisted:
                raise ValueError(
                    "chunk content factory created ECS entities not listed in ChunkContent.entities"
                )
            return scene.mount(*content.objects, entities=content.entities)
        except Exception:
            if content is not None:
                for obj in reversed(content.objects):
                    scene.remove(obj)
            for entity in tuple(scene.entities):
                if entity.id not in before_ids:
                    scene.ecs.destroy(entity)
            raise

    def rollback(_scene: Scene, token: object) -> None:
        if not isinstance(token, SceneMount):
            raise TypeError("invalid ChunkContent activation token")
        token.unmount()

    return SceneActivationStep(step_id=step_id, apply=apply, rollback=rollback, label=label)
