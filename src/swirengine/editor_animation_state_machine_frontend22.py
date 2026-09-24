from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from .animation15 import (
    AnimationCondition,
    AnimationParameter,
    AnimationParameters,
    ConditionOperator,
    ParameterKind,
)
from .animation_state_machine22 import AnimationStateMachinePlayer22
from .editor_animation_state_machine22 import (
    AnimationMachineEditorSession22,
    AnimationStateNode22,
    AnimationTransitionSpec22,
    BlendChildSpec22,
    TransitionConditionSpec22,
)
from .graphics.skeletal import SkeletalAnimationClip3D, SkeletalPose, Skeleton3D

_UNSET = object()


@dataclass(frozen=True, slots=True)
class AnimationStateRow22:
    name: str
    x: float
    y: float
    motion: str
    initial: bool
    speed: float
    loop: bool


@dataclass(frozen=True, slots=True)
class AnimationParameterRow22:
    name: str
    kind: str
    default: Any


@dataclass(frozen=True, slots=True)
class AnimationTransitionRow22:
    index: int
    source: str
    target: str
    conditions: tuple[str, ...]
    duration: float
    exit_time: float | None
    priority: int


@dataclass(frozen=True, slots=True)
class RigNodePreview22:
    index: int
    parent: int | None
    name: str
    translation: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class AnimationMachineEditorFrame22:
    asset_name: str
    selected_state: str | None
    states: tuple[AnimationStateRow22, ...]
    parameters: tuple[AnimationParameterRow22, ...]
    transitions: tuple[AnimationTransitionRow22, ...]
    dirty: bool
    diagnostics: tuple[str, ...]
    preview_active: bool
    preview_state: str | None
    preview_next_state: str | None
    preview_normalized_time: float | None
    preview_parameters: tuple[tuple[str, Any], ...]
    rig: tuple[RigNodePreview22, ...]


class AnimationMachinePanelController22:
    """Toolkit-neutral M5 controller for graph authoring and runtime-backed preview."""

    def __init__(self, session: AnimationMachineEditorSession22) -> None:
        if not isinstance(session, AnimationMachineEditorSession22):
            raise TypeError("session must be AnimationMachineEditorSession22")
        self.session = session
        self._selected_state = session.document.initial
        self._status = "Animation State Machine / Blend Tree ready"
        self._skeleton: Skeleton3D | None = None
        self._clips: Mapping[str, SkeletalAnimationClip3D] | None = None
        self._player: AnimationStateMachinePlayer22 | None = None
        self._pose: SkeletalPose | None = None

    @property
    def status(self) -> str:
        return self._status

    @property
    def selected_state(self) -> AnimationStateNode22:
        if self._selected_state is None:
            raise RuntimeError("no animation state is selected")
        return self._state(self._selected_state)

    def frame(self) -> AnimationMachineEditorFrame22:
        document = self.session.document
        names = {state.name for state in document.states}
        if self._selected_state not in names:
            self._selected_state = document.initial
        player = self._player
        return AnimationMachineEditorFrame22(
            asset_name=self.session.asset_name,
            selected_state=self._selected_state,
            states=tuple(
                AnimationStateRow22(
                    state.name,
                    state.x,
                    state.y,
                    self._motion_label(state),
                    state.name == document.initial,
                    state.speed,
                    state.loop,
                )
                for state in document.states
            ),
            parameters=tuple(
                AnimationParameterRow22(item.name, item.kind.value, item.default)
                for item in document.parameters
            ),
            transitions=tuple(
                AnimationTransitionRow22(
                    index,
                    item.source,
                    item.target,
                    tuple(self._condition_label(condition) for condition in item.conditions),
                    item.duration,
                    item.exit_time,
                    item.priority,
                )
                for index, item in enumerate(document.transitions)
            ),
            dirty=self.session.dirty,
            diagnostics=self.diagnostics(),
            preview_active=player is not None,
            preview_state=None if player is None else player.current,
            preview_next_state=None if player is None else player.next_state,
            preview_normalized_time=None if player is None else player.normalized_time,
            preview_parameters=(
                ()
                if player is None
                else tuple(sorted(player.parameters.snapshot().items()))
            ),
            rig=self._rig_snapshot(),
        )

    def select_state(self, name: str) -> AnimationMachineEditorFrame22:
        self._selected_state = self._state(name).name
        self._status = f"Selected animation state {self._selected_state}"
        return self.frame()

    def add_clip_state(
        self,
        name: str,
        clip: str,
        *,
        x: float = 80.0,
        y: float = 80.0,
        speed: float = 1.0,
        loop: bool = True,
    ) -> AnimationMachineEditorFrame22:
        self._ensure_new_state(name)
        state = AnimationStateNode22(name, x=x, y=y, clip=clip, speed=speed, loop=loop)
        self._set_document(states=(*self.session.document.states, state))
        self._selected_state = state.name
        self._status = f"Added clip state {state.name}"
        return self.frame()

    def add_blend_state(
        self,
        name: str,
        parameter: str,
        children: Sequence[BlendChildSpec22],
        *,
        x: float = 80.0,
        y: float = 80.0,
        speed: float = 1.0,
        loop: bool = True,
    ) -> AnimationMachineEditorFrame22:
        self._ensure_new_state(name)
        self._require_numeric_parameter(parameter)
        state = AnimationStateNode22(
            name,
            x=x,
            y=y,
            blend_parameter=parameter,
            blend_children=tuple(children),
            speed=speed,
            loop=loop,
        )
        self._set_document(states=(*self.session.document.states, state))
        self._selected_state = state.name
        self._status = f"Added 1D blend state {state.name}"
        return self.frame()

    def configure_clip_state(
        self,
        name: str,
        clip: str,
        *,
        speed: float | None = None,
        loop: bool | None = None,
    ) -> AnimationMachineEditorFrame22:
        state = self._state(name)
        self._replace_state(
            state.name,
            replace(
                state,
                clip=clip,
                blend_parameter=None,
                blend_children=(),
                speed=state.speed if speed is None else speed,
                loop=state.loop if loop is None else bool(loop),
            ),
        )
        self._status = f"Configured clip motion for {state.name}"
        return self.frame()

    def configure_blend_state(
        self,
        name: str,
        parameter: str,
        children: Sequence[BlendChildSpec22],
        *,
        speed: float | None = None,
        loop: bool | None = None,
    ) -> AnimationMachineEditorFrame22:
        state = self._state(name)
        self._require_numeric_parameter(parameter)
        self._replace_state(
            state.name,
            replace(
                state,
                clip=None,
                blend_parameter=parameter,
                blend_children=tuple(children),
                speed=state.speed if speed is None else speed,
                loop=state.loop if loop is None else bool(loop),
            ),
        )
        self._status = f"Configured 1D blend tree for {state.name}"
        return self.frame()

    def move_state(self, name: str, x: float, y: float) -> AnimationMachineEditorFrame22:
        state = self._state(name)
        self._replace_state(state.name, replace(state, x=x, y=y))
        self._status = f"Moved animation state {state.name}"
        return self.frame()

    def rename_state(self, name: str, new_name: str) -> AnimationMachineEditorFrame22:
        state = self._state(name)
        if str(new_name).strip() != state.name:
            self._ensure_new_state(new_name)
        renamed = replace(state, name=new_name)
        resolved = renamed.name
        states = tuple(
            renamed if item.name == state.name else item
            for item in self.session.document.states
        )
        transitions = tuple(
            replace(
                item,
                source=resolved if item.source == state.name else item.source,
                target=resolved if item.target == state.name else item.target,
            )
            for item in self.session.document.transitions
        )
        initial = (
            resolved
            if self.session.document.initial == state.name
            else self.session.document.initial
        )
        self._set_document(states=states, transitions=transitions, initial=initial)
        self._selected_state = resolved
        self._status = f"Renamed animation state {state.name} → {resolved}"
        return self.frame()

    def remove_state(self, name: str) -> AnimationMachineEditorFrame22:
        state = self._state(name)
        if len(self.session.document.states) <= 1:
            raise ValueError("animation machine must keep at least one state")
        states = tuple(item for item in self.session.document.states if item.name != state.name)
        transitions = tuple(
            item
            for item in self.session.document.transitions
            if item.source != state.name and item.target != state.name
        )
        initial = self.session.document.initial
        if initial == state.name:
            initial = states[0].name
        self._set_document(states=states, transitions=transitions, initial=initial)
        self._selected_state = initial
        self._status = f"Removed animation state {state.name}"
        return self.frame()

    def set_initial(self, name: str) -> AnimationMachineEditorFrame22:
        state = self._state(name)
        self._set_document(initial=state.name)
        self._status = f"Set initial animation state to {state.name}"
        return self.frame()

    def add_parameter(
        self,
        name: str,
        kind: ParameterKind | str,
        default: Any = None,
    ) -> AnimationMachineEditorFrame22:
        normalized = str(name).strip()
        if any(item.name == normalized for item in self.session.document.parameters):
            raise ValueError(f"animation parameter already exists: {normalized}")
        parameter = AnimationParameter(normalized, kind, default)
        self._set_document(parameters=(*self.session.document.parameters, parameter))
        self._status = f"Added animation parameter {parameter.name}"
        return self.frame()

    def rename_parameter(self, name: str, new_name: str) -> AnimationMachineEditorFrame22:
        parameter = self._parameter(name)
        replacement = AnimationParameter(new_name, parameter.kind, parameter.default)
        if replacement.name != parameter.name and any(
            item.name == replacement.name for item in self.session.document.parameters
        ):
            raise ValueError(f"animation parameter already exists: {replacement.name}")
        parameters = tuple(
            replacement if item.name == parameter.name else item
            for item in self.session.document.parameters
        )
        states = tuple(
            replace(state, blend_parameter=replacement.name)
            if state.blend_parameter == parameter.name
            else state
            for state in self.session.document.states
        )
        transitions = tuple(
            replace(
                item,
                conditions=tuple(
                    replace(condition, parameter=replacement.name)
                    if condition.parameter == parameter.name
                    else condition
                    for condition in item.conditions
                ),
            )
            for item in self.session.document.transitions
        )
        self._set_document(parameters=parameters, states=states, transitions=transitions)
        self._status = f"Renamed animation parameter {parameter.name} → {replacement.name}"
        return self.frame()

    def set_parameter_default(self, name: str, value: Any) -> AnimationMachineEditorFrame22:
        parameter = self._parameter(name)
        replacement = AnimationParameter(parameter.name, parameter.kind, value)
        self._set_document(
            parameters=tuple(
                replacement if item.name == parameter.name else item
                for item in self.session.document.parameters
            )
        )
        self._status = f"Updated default for animation parameter {parameter.name}"
        return self.frame()

    def remove_parameter(self, name: str) -> AnimationMachineEditorFrame22:
        parameter = self._parameter(name)
        for state in self.session.document.states:
            if state.blend_parameter == parameter.name:
                raise ValueError(
                    f"animation parameter {parameter.name!r} is used by blend state {state.name!r}"
                )
        if any(
            condition.parameter == parameter.name
            for transition in self.session.document.transitions
            for condition in transition.conditions
        ):
            raise ValueError(f"animation parameter {parameter.name!r} is used by a transition")
        self._set_document(
            parameters=tuple(
                item for item in self.session.document.parameters if item.name != parameter.name
            )
        )
        self._status = f"Removed animation parameter {parameter.name}"
        return self.frame()

    def add_transition(
        self,
        source: str,
        target: str,
        *,
        conditions: Sequence[TransitionConditionSpec22] = (),
        duration: float = 0.0,
        exit_time: float | None = None,
        priority: int = 0,
    ) -> AnimationMachineEditorFrame22:
        transition = self._validated_transition(
            source,
            target,
            conditions=conditions,
            duration=duration,
            exit_time=exit_time,
            priority=priority,
        )
        self._set_document(transitions=(*self.session.document.transitions, transition))
        self._status = f"Added transition {transition.source} → {transition.target}"
        return self.frame()

    def update_transition(
        self,
        index: int,
        *,
        source: str | None = None,
        target: str | None = None,
        conditions: Sequence[TransitionConditionSpec22] | None = None,
        duration: float | None = None,
        exit_time: object = _UNSET,
        priority: int | None = None,
    ) -> AnimationMachineEditorFrame22:
        transition = self._transition(index)
        updated = self._validated_transition(
            transition.source if source is None else source,
            transition.target if target is None else target,
            conditions=transition.conditions if conditions is None else conditions,
            duration=transition.duration if duration is None else duration,
            exit_time=transition.exit_time if exit_time is _UNSET else exit_time,
            priority=transition.priority if priority is None else priority,
        )
        transitions = list(self.session.document.transitions)
        transitions[index] = updated
        self._set_document(transitions=tuple(transitions))
        self._status = f"Updated transition {index}: {updated.source} → {updated.target}"
        return self.frame()

    def remove_transition(self, index: int) -> AnimationMachineEditorFrame22:
        transition = self._transition(index)
        self._set_document(
            transitions=tuple(
                item
                for item_index, item in enumerate(self.session.document.transitions)
                if item_index != index
            )
        )
        self._status = f"Removed transition {transition.source} → {transition.target}"
        return self.frame()

    def diagnostics(self) -> tuple[str, ...]:
        document = self.session.document
        state_names = {state.name for state in document.states}
        parameters = {item.name: item for item in document.parameters}
        issues: list[str] = []
        for state in document.states:
            if state.blend_parameter is None:
                continue
            parameter = parameters.get(state.blend_parameter)
            if parameter is None:
                issues.append(
                    f"state {state.name!r} references unknown blend parameter "
                    f"{state.blend_parameter!r}"
                )
            elif parameter.kind not in {ParameterKind.FLOAT, ParameterKind.INT}:
                issues.append(
                    f"state {state.name!r} blend parameter {parameter.name!r} must be numeric"
                )
        probe = AnimationParameters(document.parameters)
        for index, transition in enumerate(document.transitions):
            if transition.source != "*" and transition.source not in state_names:
                issues.append(f"transition {index} has unknown source {transition.source!r}")
            if transition.target not in state_names:
                issues.append(f"transition {index} has unknown target {transition.target!r}")
            if transition.source == transition.target:
                issues.append(f"transition {index} is a disabled self-transition")
            for condition in transition.conditions:
                try:
                    AnimationCondition(
                        condition.parameter,
                        condition.operator,
                        condition.value,
                    ).evaluate(probe)
                except (KeyError, TypeError, ValueError) as exc:
                    issues.append(f"transition {index}: {exc}")
        return tuple(issues)

    def validate_runtime(
        self,
        skeleton: Skeleton3D,
        clips: Mapping[str, SkeletalAnimationClip3D],
    ) -> tuple[str, ...]:
        issues = list(self.diagnostics())
        try:
            self.session.compile(skeleton, clips)
        except (KeyError, TypeError, ValueError) as exc:
            issues.append(str(exc))
        return tuple(dict.fromkeys(issues))

    def start_preview(
        self,
        skeleton: Skeleton3D,
        clips: Mapping[str, SkeletalAnimationClip3D],
    ) -> AnimationMachineEditorFrame22:
        self._skeleton = skeleton
        self._clips = dict(clips)
        self._player = self.session.compile(skeleton, clips).player()
        self._pose = self._player.sample()
        self._status = f"Preview started in {self._player.current}"
        return self.frame()

    def stop_preview(self) -> AnimationMachineEditorFrame22:
        self._invalidate_preview()
        self._status = "Preview stopped"
        return self.frame()

    def restart_preview(self) -> AnimationMachineEditorFrame22:
        if self._skeleton is None or self._clips is None:
            raise RuntimeError("preview resources are not bound")
        return self.start_preview(self._skeleton, self._clips)

    def step_preview(self, dt: float) -> AnimationMachineEditorFrame22:
        player = self._require_player()
        self._pose = player.update(dt)
        self._status = f"Preview {player.current} at {player.normalized_time:.3f}"
        return self.frame()

    def set_preview_parameter(self, name: str, value: Any) -> AnimationMachineEditorFrame22:
        player = self._require_player()
        player.set_parameter(name, value)
        self._pose = player.sample()
        self._status = f"Preview parameter {name} = {value!r}"
        return self.frame()

    def trigger_preview(self, name: str) -> AnimationMachineEditorFrame22:
        self._require_player().trigger(name)
        self._status = f"Preview trigger {name} armed"
        return self.frame()

    def force_preview_state(self, name: str) -> AnimationMachineEditorFrame22:
        player = self._require_player()
        player.force_state(name)
        self._pose = player.sample()
        self._status = f"Preview forced to {name}"
        return self.frame()

    def save(self) -> AnimationMachineEditorFrame22:
        self.session.save()
        self._status = f"Saved animation machine {self.session.asset_name}"
        return self.frame()

    def _set_document(self, **changes: Any) -> None:
        self.session.document = replace(self.session.document, **changes)
        self.session.dirty = True
        self._invalidate_preview(keep_resources=True)

    def _replace_state(self, name: str, replacement: AnimationStateNode22) -> None:
        self._set_document(
            states=tuple(
                replacement if state.name == name else state
                for state in self.session.document.states
            )
        )

    def _state(self, name: str) -> AnimationStateNode22:
        normalized = str(name).strip()
        for state in self.session.document.states:
            if state.name == normalized:
                return state
        raise KeyError(f"unknown animation state: {normalized}")

    def _parameter(self, name: str) -> AnimationParameter:
        normalized = str(name).strip()
        for parameter in self.session.document.parameters:
            if parameter.name == normalized:
                return parameter
        raise KeyError(f"unknown animation parameter: {normalized}")

    def _transition(self, index: int) -> AnimationTransitionSpec22:
        if not isinstance(index, int) or isinstance(index, bool):
            raise TypeError("transition index must be int")
        if index < 0 or index >= len(self.session.document.transitions):
            raise IndexError(f"unknown animation transition index: {index}")
        return self.session.document.transitions[index]

    def _ensure_new_state(self, name: str) -> None:
        normalized = str(name).strip()
        if any(state.name == normalized for state in self.session.document.states):
            raise ValueError(f"animation state already exists: {normalized}")

    def _require_numeric_parameter(self, name: str) -> AnimationParameter:
        parameter = self._parameter(name)
        if parameter.kind not in {ParameterKind.FLOAT, ParameterKind.INT}:
            raise TypeError(f"blend parameter {parameter.name!r} must be numeric")
        return parameter

    def _validated_transition(
        self,
        source: str,
        target: str,
        *,
        conditions: Sequence[TransitionConditionSpec22],
        duration: float,
        exit_time: object,
        priority: int,
    ) -> AnimationTransitionSpec22:
        source_name = str(source).strip()
        target_name = self._state(target).name
        if source_name != "*":
            source_name = self._state(source_name).name
        if source_name == target_name:
            raise ValueError("self-transitions are not enabled by the M5 creator asset contract")
        condition_specs = tuple(conditions)
        probe = AnimationParameters(self.session.document.parameters)
        for condition in condition_specs:
            AnimationCondition(
                condition.parameter,
                condition.operator,
                condition.value,
            ).evaluate(probe)
        return AnimationTransitionSpec22(
            source_name,
            target_name,
            conditions=condition_specs,
            duration=duration,
            exit_time=None if exit_time is None else float(exit_time),
            priority=priority,
        )

    def _require_player(self) -> AnimationStateMachinePlayer22:
        if self._player is None:
            raise RuntimeError("animation machine preview is not active")
        return self._player

    def _invalidate_preview(self, *, keep_resources: bool = False) -> None:
        self._player = None
        self._pose = None
        if not keep_resources:
            self._skeleton = None
            self._clips = None

    def _rig_snapshot(self) -> tuple[RigNodePreview22, ...]:
        if self._pose is None or self._skeleton is None:
            return ()
        return tuple(
            RigNodePreview22(
                node.index,
                node.parent,
                node.name or f"node_{node.index}",
                tuple(float(value) for value in self._pose.translations[node.index]),
            )
            for node in self._skeleton.nodes
        )

    @staticmethod
    def _motion_label(state: AnimationStateNode22) -> str:
        if state.clip is not None:
            return f"clip:{state.clip}"
        assert state.blend_parameter is not None
        return f"blend1d:{state.blend_parameter} ({len(state.blend_children)})"

    @staticmethod
    def _condition_label(condition: TransitionConditionSpec22) -> str:
        operator = ConditionOperator(condition.operator).value
        if operator in {
            ConditionOperator.TRUE.value,
            ConditionOperator.FALSE.value,
            ConditionOperator.TRIGGER.value,
        }:
            return f"{condition.parameter} {operator}"
        return f"{condition.parameter} {operator} {condition.value!r}"
