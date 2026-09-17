from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Protocol

from .graphics.batching import SpriteBatch, build_render_runs
from .graphics.camera3d import Camera3D
from .graphics.instancing import InstancedMesh3D
from .graphics.primitives import Rectangle2D, Text2D
from .graphics.renderer2 import Renderer2FramePlan, Renderer2Planner, Renderer2Settings
from .render_graph18 import RenderGraphBuilder, RenderGraphPlan
from .render_quality18 import DynamicQualityController, RenderQualityStep

BridgeMode = Literal["2d", "3d"]
BridgeExecution = Literal["graph-backend", "graph-compat", "fallback"]
RenderRunKind = Literal["sprite_batch", "rectangle", "text"]


class Renderer2BridgeError(RuntimeError):
    """Stable creator-facing failure raised by the Renderer2 1.8 compatibility bridge."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class GraphRenderBackend(Protocol):
    """Optional backend hook for a native render-graph execution path."""

    def render_graph18(
        self,
        frame: Renderer2BridgeFrame,
        scene: object,
        *,
        camera: object | None,
        clear_color: tuple[float, float, float, float],
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class Renderer2BridgeSettings:
    """Hard bounds and fallback policy for the additive Renderer2 integration layer."""

    max_passes: int = 2048
    max_resources: int = 4096
    max_2d_runs: int = 2048
    allow_compat_execution: bool = True
    fallback_on_prepare_error: bool = True

    def __post_init__(self) -> None:
        for name in ("max_passes", "max_resources", "max_2d_runs"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value < 1:
                raise ValueError(f"{name} must be >= 1")
        if not isinstance(self.allow_compat_execution, bool):
            raise TypeError("allow_compat_execution must be a boolean")
        if not isinstance(self.fallback_on_prepare_error, bool):
            raise TypeError("fallback_on_prepare_error must be a boolean")


@dataclass(frozen=True, slots=True)
class Renderer2RunSummary:
    kind: RenderRunKind
    count: int
    layer: int
    screen_space: bool
    content_fingerprint: str

    def portable(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "count": self.count,
            "layer": self.layer,
            "screen_space": self.screen_space,
            "content_fingerprint": self.content_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class Renderer2BridgeFrame:
    """Portable graph-backed frame contract created before GPU submission."""

    mode: BridgeMode
    width: int
    height: int
    graph: RenderGraphPlan
    renderer2_plan: Renderer2FramePlan | None
    runs_2d: tuple[Renderer2RunSummary, ...]
    instanced_batches: int
    instanced_instances: int
    quality_step: RenderQualityStep | None
    graph_backend_available: bool
    fingerprint: str

    def portable(self) -> MappingProxyType[str, object]:
        return MappingProxyType(
            {
                "mode": self.mode,
                "width": self.width,
                "height": self.height,
                "graph": dict(self.graph.portable()),
                "renderer2_passes": []
                if self.renderer2_plan is None
                else [item.name for item in self.renderer2_plan.passes],
                "runs_2d": [run.portable() for run in self.runs_2d],
                "instanced_batches": self.instanced_batches,
                "instanced_instances": self.instanced_instances,
                "quality_step": None
                if self.quality_step is None
                else self.quality_step.portable(),
                "graph_backend_available": self.graph_backend_available,
                "fingerprint": self.fingerprint,
            }
        )


@dataclass(frozen=True, slots=True)
class Renderer2BridgeResult:
    execution: BridgeExecution
    frame: Renderer2BridgeFrame | None
    fallback_reason: str | None


@dataclass(frozen=True, slots=True)
class Renderer2BridgeDiagnostics:
    prepared_frames: int
    graph_backend_frames: int
    graph_compat_frames: int
    fallback_frames: int
    prepare_failures: int
    last_graph_passes: int
    last_graph_resources: int
    last_2d_runs: int
    last_instanced_batches: int
    last_instanced_instances: int
    last_execution: BridgeExecution | None

    def portable(self) -> MappingProxyType[str, int | str | None]:
        return MappingProxyType(
            {
                "prepared_frames": self.prepared_frames,
                "graph_backend_frames": self.graph_backend_frames,
                "graph_compat_frames": self.graph_compat_frames,
                "fallback_frames": self.fallback_frames,
                "prepare_failures": self.prepare_failures,
                "last_graph_passes": self.last_graph_passes,
                "last_graph_resources": self.last_graph_resources,
                "last_2d_runs": self.last_2d_runs,
                "last_instanced_batches": self.last_instanced_batches,
                "last_instanced_instances": self.last_instanced_instances,
                "last_execution": self.last_execution,
            }
        )


def _positive_dimension(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if value < 1:
        raise ValueError(f"{label} must be >= 1")
    return value


def _renderer_mode(renderer: object) -> BridgeMode:
    mode = getattr(renderer, "mode", None)
    if mode not in {"2d", "3d"}:
        raise Renderer2BridgeError(
            "unsupported-mode",
            "renderer mode must be '2d' or '3d' for the Renderer2 1.8 bridge",
        )
    return mode


def _content_token(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def _chain_graph(
    stage_names: tuple[str, ...],
    *,
    max_passes: int,
    max_resources: int,
) -> RenderGraphPlan:
    builder = RenderGraphBuilder(max_passes=max_passes, max_resources=max_resources)
    stages = stage_names or ("clear",)
    previous: str | None = None
    for index, stage in enumerate(stages):
        resource = f"frame_{index:04d}"
        builder.add_resource(resource, transient=True, size_bytes=0)
        reads = () if previous is None else (previous,)
        builder.add_pass(
            f"stage_{index:04d}_{stage}",
            reads=reads,
            writes=(resource,),
            priority=index,
        )
        previous = resource
    assert previous is not None
    builder.mark_output(previous)
    return builder.compile()


def _frame_fingerprint(
    *,
    mode: BridgeMode,
    width: int,
    height: int,
    graph: RenderGraphPlan,
    runs_2d: tuple[Renderer2RunSummary, ...],
    renderer2_plan: Renderer2FramePlan | None,
    instanced_batches: int,
    instanced_instances: int,
    quality_step: RenderQualityStep | None,
    graph_backend_available: bool,
) -> str:
    payload = {
        "mode": mode,
        "width": width,
        "height": height,
        "graph": graph.fingerprint,
        "runs_2d": [run.portable() for run in runs_2d],
        "renderer2_passes": []
        if renderer2_plan is None
        else [item.name for item in renderer2_plan.passes],
        "instanced_batches": instanced_batches,
        "instanced_instances": instanced_instances,
        "quality_step": None if quality_step is None else quality_step.portable(),
        "graph_backend_available": graph_backend_available,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class Renderer2BridgeCompiler:
    """Build deterministic graph contracts for existing SwirEngine renderer capabilities."""

    def __init__(
        self,
        *,
        settings: Renderer2BridgeSettings | None = None,
        quality: DynamicQualityController | None = None,
    ) -> None:
        self.settings = settings or Renderer2BridgeSettings()
        if not isinstance(self.settings, Renderer2BridgeSettings):
            raise TypeError("settings must be Renderer2BridgeSettings or None")
        if quality is not None and not isinstance(quality, DynamicQualityController):
            raise TypeError("quality must be DynamicQualityController or None")
        self.quality = quality

    @staticmethod
    def _sprite_token(item: SpriteBatch) -> str:
        key = item.key
        return _content_token(
            {
                "texture": str(key.texture),
                "filtering": str(key.filtering),
                "blend": str(key.blend),
                "layer": int(key.layer),
                "screen_space": bool(key.screen_space),
            }
        )

    @staticmethod
    def _rectangle_token(item: Rectangle2D) -> str:
        return _content_token(
            {
                "x": item.x,
                "y": item.y,
                "width": item.width,
                "height": item.height,
                "color": item.color,
            }
        )

    @staticmethod
    def _text_token(item: Text2D) -> str:
        return _content_token(
            {
                "text": item.text,
                "font": item.font,
                "font_size": item.font_size,
                "color": item.color,
                "anchor": item.anchor,
            }
        )

    def _2d_runs(self, scene: object) -> tuple[Renderer2RunSummary, ...]:
        objects = sorted(
            getattr(scene, "objects", ()),
            key=lambda item: int(getattr(item, "layer", 0)),
        )
        result: list[Renderer2RunSummary] = []
        for item in build_render_runs(objects):
            if len(result) >= self.settings.max_2d_runs:
                raise Renderer2BridgeError(
                    "2d-run-limit",
                    "2D render run count exceeds Renderer2 bridge max_2d_runs",
                )
            if isinstance(item, SpriteBatch):
                result.append(
                    Renderer2RunSummary(
                        "sprite_batch",
                        len(item.sprites),
                        int(item.key.layer),
                        bool(item.key.screen_space),
                        self._sprite_token(item),
                    )
                )
            elif isinstance(item, Rectangle2D):
                result.append(
                    Renderer2RunSummary(
                        "rectangle",
                        1,
                        int(item.layer),
                        bool(item.screen_space),
                        self._rectangle_token(item),
                    )
                )
            elif isinstance(item, Text2D):
                result.append(
                    Renderer2RunSummary(
                        "text",
                        1,
                        int(item.layer),
                        bool(item.screen_space),
                        self._text_token(item),
                    )
                )
        return tuple(result)

    @staticmethod
    def _instancing(scene: object) -> tuple[int, int]:
        batches = 0
        instances = 0
        for item in getattr(scene, "objects", ()):
            if not isinstance(item, InstancedMesh3D):
                continue
            if not getattr(item, "enabled", True) or not getattr(item, "visible", True):
                continue
            batches += 1
            instances += sum(
                1
                for instance in item.instances
                if getattr(instance, "enabled", True) and getattr(instance, "visible", True)
            )
        return batches, instances

    def prepare(
        self,
        renderer: object,
        scene: object,
        *,
        camera: object | None = None,
    ) -> Renderer2BridgeFrame:
        mode = _renderer_mode(renderer)
        width = _positive_dimension(getattr(renderer, "width", None), label="renderer width")
        height = _positive_dimension(getattr(renderer, "height", None), label="renderer height")
        graph_backend_available = callable(getattr(renderer, "render_graph18", None))
        quality_step = None if self.quality is None else self.quality.current_step
        instanced_batches, instanced_instances = self._instancing(scene)

        renderer2_plan: Renderer2FramePlan | None = None
        runs_2d: tuple[Renderer2RunSummary, ...] = ()
        if mode == "2d":
            runs_2d = self._2d_runs(scene)
            stage_names = tuple(run.kind for run in runs_2d)
        else:
            active_camera = camera if isinstance(camera, Camera3D) else Camera3D()
            authored = getattr(renderer, "renderer2", None)
            settings = authored if isinstance(authored, Renderer2Settings) else Renderer2Settings()
            renderer2_plan = Renderer2Planner(settings).plan(
                scene,
                active_camera,
                width=width,
                height=height,
            )
            stage_names = tuple(item.name for item in renderer2_plan.passes)
            if instanced_batches:
                stage_names += ("instancing_compat",)

        graph = _chain_graph(
            stage_names,
            max_passes=self.settings.max_passes,
            max_resources=self.settings.max_resources,
        )
        fingerprint = _frame_fingerprint(
            mode=mode,
            width=width,
            height=height,
            graph=graph,
            runs_2d=runs_2d,
            renderer2_plan=renderer2_plan,
            instanced_batches=instanced_batches,
            instanced_instances=instanced_instances,
            quality_step=quality_step,
            graph_backend_available=graph_backend_available,
        )
        return Renderer2BridgeFrame(
            mode=mode,
            width=width,
            height=height,
            graph=graph,
            renderer2_plan=renderer2_plan,
            runs_2d=runs_2d,
            instanced_batches=instanced_batches,
            instanced_instances=instanced_instances,
            quality_step=quality_step,
            graph_backend_available=graph_backend_available,
            fingerprint=fingerprint,
        )


class Renderer2CompatibilityBridge:
    """Opt-in graph-backed compatibility front-end for stable 1.x renderers.

    The bridge never changes the root/public Renderer API. A backend that implements
    ``render_graph18`` receives the compiled frame directly. Existing renderers use a graph-validated
    compatibility execution that calls their historical ``render`` method exactly once. Preparation
    failures can explicitly fall back to the historical path, so opting into the bridge never forces a
    backend capability that is not available.
    """

    def __init__(
        self,
        renderer: object,
        *,
        settings: Renderer2BridgeSettings | None = None,
        quality: DynamicQualityController | None = None,
    ) -> None:
        render = getattr(renderer, "render", None)
        graph_render = getattr(renderer, "render_graph18", None)
        if not callable(render) and not callable(graph_render):
            raise TypeError("renderer must expose render() or render_graph18()")
        self.renderer = renderer
        self.compiler = Renderer2BridgeCompiler(settings=settings, quality=quality)
        self._prepared_frames = 0
        self._graph_backend_frames = 0
        self._graph_compat_frames = 0
        self._fallback_frames = 0
        self._prepare_failures = 0
        self._last_result: Renderer2BridgeResult | None = None

    @property
    def last_result(self) -> Renderer2BridgeResult | None:
        return self._last_result

    def prepare(self, scene: object, *, camera: object | None = None) -> Renderer2BridgeFrame:
        frame = self.compiler.prepare(self.renderer, scene, camera=camera)
        self._prepared_frames += 1
        return frame

    def render(
        self,
        scene: object,
        *,
        camera: object | None = None,
        clear_color: tuple[float, float, float, float] = (0.035, 0.045, 0.07, 1.0),
    ) -> Renderer2BridgeResult:
        try:
            frame = self.prepare(scene, camera=camera)
        except (Renderer2BridgeError, TypeError, ValueError) as exc:
            self._prepare_failures += 1
            if not self.compiler.settings.fallback_on_prepare_error:
                raise
            render = getattr(self.renderer, "render", None)
            if not callable(render):
                raise Renderer2BridgeError(
                    "fallback-unavailable",
                    "render graph preparation failed and renderer has no legacy render() fallback",
                ) from exc
            render(scene, camera=camera, clear_color=clear_color)
            self._fallback_frames += 1
            result = Renderer2BridgeResult("fallback", None, str(exc))
            self._last_result = result
            return result

        graph_render = getattr(self.renderer, "render_graph18", None)
        if callable(graph_render):
            graph_render(
                frame,
                scene,
                camera=camera,
                clear_color=clear_color,
            )
            self._graph_backend_frames += 1
            result = Renderer2BridgeResult("graph-backend", frame, None)
            self._last_result = result
            return result

        if not self.compiler.settings.allow_compat_execution:
            render = getattr(self.renderer, "render", None)
            if not callable(render):
                raise Renderer2BridgeError(
                    "compat-unavailable",
                    "renderer has no graph backend and no render() compatibility path",
                )
            render(scene, camera=camera, clear_color=clear_color)
            self._fallback_frames += 1
            result = Renderer2BridgeResult(
                "fallback",
                frame,
                "native render_graph18 backend unavailable",
            )
            self._last_result = result
            return result

        render = getattr(self.renderer, "render", None)
        if not callable(render):
            raise Renderer2BridgeError(
                "compat-unavailable",
                "renderer has no render() method for graph-validated compatibility execution",
            )
        render(scene, camera=camera, clear_color=clear_color)
        self._graph_compat_frames += 1
        result = Renderer2BridgeResult("graph-compat", frame, None)
        self._last_result = result
        return result

    def diagnostics(self) -> Renderer2BridgeDiagnostics:
        frame = None if self._last_result is None else self._last_result.frame
        graph = None if frame is None else frame.graph
        return Renderer2BridgeDiagnostics(
            prepared_frames=self._prepared_frames,
            graph_backend_frames=self._graph_backend_frames,
            graph_compat_frames=self._graph_compat_frames,
            fallback_frames=self._fallback_frames,
            prepare_failures=self._prepare_failures,
            last_graph_passes=0 if graph is None else graph.diagnostics.active_passes,
            last_graph_resources=0 if graph is None else graph.diagnostics.active_resources,
            last_2d_runs=0 if frame is None else len(frame.runs_2d),
            last_instanced_batches=0 if frame is None else frame.instanced_batches,
            last_instanced_instances=0 if frame is None else frame.instanced_instances,
            last_execution=None if self._last_result is None else self._last_result.execution,
        )
