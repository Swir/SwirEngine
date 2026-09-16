from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .graphics.camera3d import Camera3D
from .graphics.instancing import Frustum3D
from .graphics.mesh import Mesh3D
from .graphics.primitives import Cube3D
from .math.types import perspective
from .scene_visibility import (
    OcclusionPredicate3D,
    SceneVisibilityIndex3D,
    VisibilityQueryDiagnostics3D,
    visibility_bounds_for,
)

if TYPE_CHECKING:
    from .core.scene import Scene


@dataclass(frozen=True, slots=True)
class AcceleratedSceneView3D:
    """Small renderer-facing scene view containing only current visibility candidates."""

    objects: tuple[object, ...]

    @property
    def render_objects(self) -> tuple[object, ...]:
        return self.objects


@dataclass(frozen=True, slots=True)
class SceneAccelerationDiagnostics3D:
    """Creator-facing counters for one accelerated scene query."""

    snapshot_rebuilds: int
    indexed_entries: int
    fallback_entries: int
    query: VisibilityQueryDiagnostics3D


@dataclass(frozen=True, slots=True)
class SceneAccelerationFrame3D:
    view: AcceleratedSceneView3D
    diagnostics: SceneAccelerationDiagnostics3D


class SceneAccelerationRuntime3D:
    """Synchronize cached scene membership with a BVH visibility index.

    Scene membership uses ``Scene.render_objects`` as a stable snapshot token, so unchanged static
    scenes do not get rescanned every frame. Supported `Cube3D`/`Mesh3D` objects and objects exposing
    custom ``visibility_bounds`` enter the visibility index. Other renderer paths remain conservative
    fallback entries and are never culled here.

    Moving indexed objects must opt into dynamic refits with ``visibility_dynamic=True``. The flag is
    built into `Cube3D` and `Mesh3D`; custom objects may expose the same attribute.
    """

    def __init__(self, *, leaf_size: int = 8) -> None:
        self.index = SceneVisibilityIndex3D(leaf_size=leaf_size)
        self._snapshot: tuple[object, ...] | None = None
        self._fallback: tuple[object, ...] = ()
        self._order: dict[int, int] = {}
        self._snapshot_rebuilds = 0
        self._last_diagnostics = SceneAccelerationDiagnostics3D(
            snapshot_rebuilds=0,
            indexed_entries=0,
            fallback_entries=0,
            query=VisibilityQueryDiagnostics3D(),
        )

    @property
    def snapshot_rebuilds(self) -> int:
        return self._snapshot_rebuilds

    @property
    def diagnostics(self) -> SceneAccelerationDiagnostics3D:
        return self._last_diagnostics

    @staticmethod
    def _snapshot_for(scene: object) -> tuple[object, ...]:
        render_objects = getattr(scene, "render_objects", None)
        if render_objects is not None:
            return render_objects if isinstance(render_objects, tuple) else tuple(render_objects)
        return tuple(getattr(scene, "objects", ()))

    @staticmethod
    def _acceleratable(item: object) -> bool:
        return isinstance(item, (Cube3D, Mesh3D)) or getattr(item, "visibility_bounds", None) is not None

    def sync(self, scene: Scene | object) -> bool:
        """Rebuild membership only when the scene's cached render snapshot changes identity."""
        snapshot = self._snapshot_for(scene)
        if snapshot is self._snapshot:
            return False

        self.index.clear()
        fallback: list[object] = []
        order: dict[int, int] = {}
        for position, item in enumerate(snapshot):
            order[id(item)] = position
            if not self._acceleratable(item):
                fallback.append(item)
                continue
            self.index.add(
                item,
                bounds=visibility_bounds_for(item),
                dynamic=bool(getattr(item, "visibility_dynamic", False)),
            )

        self._snapshot = snapshot
        self._fallback = tuple(fallback)
        self._order = order
        self._snapshot_rebuilds += 1
        return True

    def frame(
        self,
        scene: Scene | object,
        camera: Camera3D,
        *,
        width: int,
        height: int,
        occlusion: OcclusionPredicate3D | None = None,
    ) -> SceneAccelerationFrame3D:
        if int(width) <= 0 or int(height) <= 0:
            raise ValueError("scene acceleration dimensions must be greater than zero")
        self.sync(scene)
        projection = perspective(
            float(camera.fov),
            float(width) / float(height),
            float(camera.near),
            float(camera.far),
        )
        frustum = Frustum3D.from_view_projection(projection @ camera.view_matrix())
        result = self.index.query(frustum, occlusion=occlusion)

        candidates = [*result.visible, *self._fallback]
        candidates.sort(key=lambda item: self._order.get(id(item), len(self._order)))
        view = AcceleratedSceneView3D(tuple(candidates))
        diagnostics = SceneAccelerationDiagnostics3D(
            snapshot_rebuilds=self._snapshot_rebuilds,
            indexed_entries=self.index.entry_count,
            fallback_entries=len(self._fallback),
            query=result.diagnostics,
        )
        self._last_diagnostics = diagnostics
        return SceneAccelerationFrame3D(view=view, diagnostics=diagnostics)


def enable_scene_acceleration(scene: Scene | object, *, leaf_size: int = 8) -> SceneAccelerationRuntime3D:
    """Attach an opt-in acceleration runtime to a scene for Renderer2-aware integrations."""
    runtime = SceneAccelerationRuntime3D(leaf_size=leaf_size)
    setattr(scene, "scene_acceleration", runtime)
    return runtime


def disable_scene_acceleration(scene: Scene | object) -> bool:
    """Remove an attached acceleration runtime and report whether one was present."""
    if not hasattr(scene, "scene_acceleration"):
        return False
    delattr(scene, "scene_acceleration")
    return True
