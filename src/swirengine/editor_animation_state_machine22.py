from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from .animation15 import (
    AnimationCondition,
    AnimationParameter,
    AnimationTransition2,
    ConditionOperator,
    ParameterKind,
)
from .animation_state_machine22 import (
    AnimationState22,
    AnimationStateMachine22,
    SkeletalBlendChild22,
    SkeletalBlendTree1D22,
)
from .graphics.skeletal import SkeletalAnimationClip3D, Skeleton3D

ANIMATION_MACHINE_FORMAT22 = "swir.animation-machine.v1"
ANIMATION_MACHINE_SUFFIX22 = ".swiranimgraph"


def _name(value: str, *, label: str) -> str:
    result = str(value).strip()
    if not result:
        raise ValueError(f"{label} cannot be empty")
    return result


def _finite(value: float, *, label: str) -> float:
    result = float(value)
    if not (-float("inf") < result < float("inf")):
        raise ValueError(f"{label} must be finite")
    return result


@dataclass(frozen=True, slots=True)
class BlendChildSpec22:
    threshold: float
    clip: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "threshold", _finite(self.threshold, label="blend threshold"))
        object.__setattr__(self, "clip", _name(self.clip, label="blend clip"))


@dataclass(frozen=True, slots=True)
class AnimationStateNode22:
    name: str
    x: float = 0.0
    y: float = 0.0
    clip: str | None = None
    blend_parameter: str | None = None
    blend_children: tuple[BlendChildSpec22, ...] = ()
    speed: float = 1.0
    loop: bool = True

    def __post_init__(self) -> None:
        name = _name(self.name, label="state name")
        x = _finite(self.x, label="state x")
        y = _finite(self.y, label="state y")
        speed = _finite(self.speed, label="state speed")
        if speed <= 0.0:
            raise ValueError("state speed must be > 0")

        clip = _name(self.clip, label="state clip") if self.clip is not None else None
        blend_parameter = (
            _name(self.blend_parameter, label="blend parameter")
            if self.blend_parameter is not None
            else None
        )
        children = tuple(self.blend_children)
        if (clip is None) == (blend_parameter is None):
            raise ValueError("state must define exactly one clip or blend tree")
        if clip is not None and children:
            raise ValueError("clip state cannot define blend children")
        if blend_parameter is not None and not children:
            raise ValueError("blend state must define at least one child")
        if len({child.threshold for child in children}) != len(children):
            raise ValueError("blend child thresholds must be unique")

        object.__setattr__(self, "name", name)
        object.__setattr__(self, "x", x)
        object.__setattr__(self, "y", y)
        object.__setattr__(self, "clip", clip)
        object.__setattr__(self, "blend_parameter", blend_parameter)
        object.__setattr__(
            self,
            "blend_children",
            tuple(sorted(children, key=lambda child: child.threshold)),
        )
        object.__setattr__(self, "speed", speed)


@dataclass(frozen=True, slots=True)
class TransitionConditionSpec22:
    parameter: str
    operator: ConditionOperator | str
    value: Any = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameter", _name(self.parameter, label="condition parameter"))
        object.__setattr__(self, "operator", ConditionOperator(self.operator))


@dataclass(frozen=True, slots=True)
class AnimationTransitionSpec22:
    source: str
    target: str
    conditions: tuple[TransitionConditionSpec22, ...] = ()
    duration: float = 0.0
    exit_time: float | None = None
    priority: int = 0

    def __post_init__(self) -> None:
        source = self.source if self.source == "*" else _name(self.source, label="transition source")
        target = _name(self.target, label="transition target")
        duration = _finite(self.duration, label="transition duration")
        if duration < 0.0:
            raise ValueError("transition duration must be >= 0")
        exit_time = self.exit_time
        if exit_time is not None:
            exit_time = _finite(exit_time, label="transition exit time")
            if not 0.0 <= exit_time <= 1.0:
                raise ValueError("transition exit time must be between 0 and 1")
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "target", target)
        object.__setattr__(self, "conditions", tuple(self.conditions))
        object.__setattr__(self, "duration", duration)
        object.__setattr__(self, "exit_time", exit_time)


@dataclass(frozen=True, slots=True)
class AnimationMachineDocument22:
    states: tuple[AnimationStateNode22, ...]
    parameters: tuple[AnimationParameter, ...] = ()
    transitions: tuple[AnimationTransitionSpec22, ...] = ()
    initial: str | None = None

    def __post_init__(self) -> None:
        states = tuple(self.states)
        if not states:
            raise ValueError("animation machine document must contain at least one state")
        names = [state.name for state in states]
        if len(set(names)) != len(names):
            raise ValueError("animation machine state names must be unique")
        parameter_names = [parameter.name for parameter in self.parameters]
        if len(set(parameter_names)) != len(parameter_names):
            raise ValueError("animation machine parameter names must be unique")
        initial = self.initial or states[0].name
        if initial not in set(names):
            raise ValueError(f"unknown initial animation state: {initial}")
        object.__setattr__(self, "states", states)
        object.__setattr__(self, "parameters", tuple(self.parameters))
        object.__setattr__(self, "transitions", tuple(self.transitions))
        object.__setattr__(self, "initial", initial)

    def move_state(self, name: str, x: float, y: float) -> AnimationMachineDocument22:
        target = _name(name, label="state name")
        moved = False
        states = []
        for state in self.states:
            if state.name == target:
                states.append(replace(state, x=x, y=y))
                moved = True
            else:
                states.append(state)
        if not moved:
            raise KeyError(f"unknown animation state: {target}")
        return replace(self, states=tuple(states))

    def compile(
        self,
        skeleton: Skeleton3D,
        clips: Mapping[str, SkeletalAnimationClip3D],
    ) -> AnimationStateMachine22:
        states = tuple(self._compile_state(state, clips) for state in self.states)
        transitions = tuple(
            AnimationTransition2(
                source=transition.source,
                target=transition.target,
                conditions=tuple(
                    AnimationCondition(
                        parameter=condition.parameter,
                        operator=condition.operator,
                        value=condition.value,
                    )
                    for condition in transition.conditions
                ),
                duration=transition.duration,
                exit_time=transition.exit_time,
                priority=transition.priority,
            )
            for transition in self.transitions
        )
        return AnimationStateMachine22(
            skeleton,
            states,
            parameters=self.parameters,
            transitions=transitions,
            initial=self.initial,
        )

    def preview(
        self,
        skeleton: Skeleton3D,
        clips: Mapping[str, SkeletalAnimationClip3D],
    ):
        return self.compile(skeleton, clips).player()

    @staticmethod
    def _compile_state(
        state: AnimationStateNode22,
        clips: Mapping[str, SkeletalAnimationClip3D],
    ) -> AnimationState22:
        if state.clip is not None:
            motion = _require_clip(clips, state.clip)
        else:
            assert state.blend_parameter is not None
            motion = SkeletalBlendTree1D22(
                state.blend_parameter,
                tuple(
                    SkeletalBlendChild22(child.threshold, _require_clip(clips, child.clip))
                    for child in state.blend_children
                ),
            )
        return AnimationState22(state.name, motion, speed=state.speed, loop=state.loop)


def _require_clip(
    clips: Mapping[str, SkeletalAnimationClip3D],
    name: str,
) -> SkeletalAnimationClip3D:
    try:
        return clips[name]
    except KeyError as exc:
        raise KeyError(f"animation machine references unknown clip: {name}") from exc


def animation_machine_document_to_dict22(document: AnimationMachineDocument22) -> dict[str, Any]:
    return {
        "format": ANIMATION_MACHINE_FORMAT22,
        "initial": document.initial,
        "parameters": [
            {
                "name": parameter.name,
                "kind": parameter.kind.value,
                "default": parameter.default,
            }
            for parameter in document.parameters
        ],
        "states": [
            {
                "name": state.name,
                "position": [state.x, state.y],
                "clip": state.clip,
                "blend": (
                    None
                    if state.blend_parameter is None
                    else {
                        "parameter": state.blend_parameter,
                        "children": [
                            {"threshold": child.threshold, "clip": child.clip}
                            for child in state.blend_children
                        ],
                    }
                ),
                "speed": state.speed,
                "loop": state.loop,
            }
            for state in document.states
        ],
        "transitions": [
            {
                "source": transition.source,
                "target": transition.target,
                "conditions": [
                    {
                        "parameter": condition.parameter,
                        "operator": condition.operator.value,
                        "value": condition.value,
                    }
                    for condition in transition.conditions
                ],
                "duration": transition.duration,
                "exit_time": transition.exit_time,
                "priority": transition.priority,
            }
            for transition in document.transitions
        ],
    }


def animation_machine_document_from_dict22(
    payload: Mapping[str, Any],
) -> AnimationMachineDocument22:
    if payload.get("format") != ANIMATION_MACHINE_FORMAT22:
        raise ValueError("unsupported animation machine format")

    parameters = tuple(
        AnimationParameter(
            _name(str(item["name"]), label="parameter name"),
            ParameterKind(str(item["kind"])),
            item.get("default"),
        )
        for item in _sequence_of_mappings(payload.get("parameters", ()), label="parameters")
    )

    states = []
    for item in _sequence_of_mappings(payload.get("states", ()), label="states"):
        position = item.get("position", (0.0, 0.0))
        if not isinstance(position, Sequence) or isinstance(position, (str, bytes)):
            raise TypeError("state position must be a sequence")
        if len(position) != 2:
            raise ValueError("state position must contain x and y")
        blend_payload = item.get("blend")
        blend_parameter = None
        blend_children: tuple[BlendChildSpec22, ...] = ()
        if blend_payload is not None:
            if not isinstance(blend_payload, Mapping):
                raise TypeError("state blend must be an object")
            blend_parameter = str(blend_payload["parameter"])
            blend_children = tuple(
                BlendChildSpec22(float(child["threshold"]), str(child["clip"]))
                for child in _sequence_of_mappings(
                    blend_payload.get("children", ()),
                    label="blend children",
                )
            )
        clip_value = item.get("clip")
        states.append(
            AnimationStateNode22(
                name=str(item["name"]),
                x=float(position[0]),
                y=float(position[1]),
                clip=None if clip_value is None else str(clip_value),
                blend_parameter=blend_parameter,
                blend_children=blend_children,
                speed=float(item.get("speed", 1.0)),
                loop=bool(item.get("loop", True)),
            )
        )

    transitions = tuple(
        AnimationTransitionSpec22(
            source=str(item["source"]),
            target=str(item["target"]),
            conditions=tuple(
                TransitionConditionSpec22(
                    str(condition["parameter"]),
                    str(condition["operator"]),
                    condition.get("value"),
                )
                for condition in _sequence_of_mappings(
                    item.get("conditions", ()),
                    label="transition conditions",
                )
            ),
            duration=float(item.get("duration", 0.0)),
            exit_time=(
                None if item.get("exit_time") is None else float(item["exit_time"])
            ),
            priority=int(item.get("priority", 0)),
        )
        for item in _sequence_of_mappings(payload.get("transitions", ()), label="transitions")
    )
    initial_value = payload.get("initial")
    return AnimationMachineDocument22(
        states=tuple(states),
        parameters=parameters,
        transitions=transitions,
        initial=None if initial_value is None else str(initial_value),
    )


def _sequence_of_mappings(value: object, *, label: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TypeError(f"{label} must be a sequence")
    result = []
    for item in value:
        if not isinstance(item, Mapping):
            raise TypeError(f"{label} entries must be objects")
        result.append(item)
    return tuple(result)


def save_animation_machine_document22(
    path: Path | str,
    document: AnimationMachineDocument22,
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            animation_machine_document_to_dict22(document),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return target


def load_animation_machine_document22(path: Path | str) -> AnimationMachineDocument22:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise TypeError("animation machine asset root must be an object")
    return animation_machine_document_from_dict22(payload)


class AnimationMachineProjectStore22:
    """Project-scoped deterministic storage for visual animation machine assets."""

    def __init__(self, project_root: Path | str) -> None:
        self.project_root = Path(project_root).resolve()
        self.asset_root = self.project_root / "assets" / "animation_machines"

    def path_for(self, asset_name: str) -> Path:
        name = _name(asset_name, label="animation machine asset")
        candidate = Path(name)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError("animation machine asset must stay inside the project")
        if candidate.suffix and candidate.suffix != ANIMATION_MACHINE_SUFFIX22:
            raise ValueError(f"animation machine asset must use {ANIMATION_MACHINE_SUFFIX22}")
        if not candidate.suffix:
            candidate = candidate.with_suffix(ANIMATION_MACHINE_SUFFIX22)
        target = (self.asset_root / candidate).resolve()
        try:
            target.relative_to(self.asset_root.resolve())
        except ValueError as exc:
            raise ValueError("animation machine asset must stay inside the project") from exc
        return target

    def save(self, asset_name: str, document: AnimationMachineDocument22) -> Path:
        return save_animation_machine_document22(self.path_for(asset_name), document)

    def load(self, asset_name: str) -> AnimationMachineDocument22:
        return load_animation_machine_document22(self.path_for(asset_name))


@dataclass(slots=True)
class AnimationMachineEditorSession22:
    """Creator-facing editing session for a visual state graph asset."""

    store: AnimationMachineProjectStore22
    asset_name: str
    document: AnimationMachineDocument22
    dirty: bool = False

    @classmethod
    def create(
        cls,
        project_root: Path | str,
        asset_name: str,
        document: AnimationMachineDocument22,
    ) -> AnimationMachineEditorSession22:
        return cls(AnimationMachineProjectStore22(project_root), asset_name, document, True)

    @classmethod
    def open(
        cls,
        project_root: Path | str,
        asset_name: str,
    ) -> AnimationMachineEditorSession22:
        store = AnimationMachineProjectStore22(project_root)
        return cls(store, asset_name, store.load(asset_name), False)

    def move_state(self, name: str, x: float, y: float) -> None:
        self.document = self.document.move_state(name, x, y)
        self.dirty = True

    def save(self) -> Path:
        path = self.store.save(self.asset_name, self.document)
        self.dirty = False
        return path

    def compile(
        self,
        skeleton: Skeleton3D,
        clips: Mapping[str, SkeletalAnimationClip3D],
    ) -> AnimationStateMachine22:
        return self.document.compile(skeleton, clips)

    def preview(
        self,
        skeleton: Skeleton3D,
        clips: Mapping[str, SkeletalAnimationClip3D],
    ):
        return self.document.preview(skeleton, clips)
