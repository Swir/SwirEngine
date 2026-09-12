from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from ..math.types import Color, Vec3
from .lights import DirectionalLight3D
from .material import Material3D
from .mesh import Mesh3D, MeshData, cube_mesh

if TYPE_CHECKING:
    from ..core.scene import Scene
    from .camera3d import Camera3D


def _scaled_rgb(color: Color, scale: float) -> Color:
    value = max(0.0, float(scale))
    return Color(color.r * value, color.g * value, color.b * value, color.a)


def _equirectangular_uvs(vertices: np.ndarray) -> np.ndarray:
    """Map cube vertices to an equirectangular panorama."""
    result = np.empty((len(vertices), 2), dtype="f4")
    for index, position in enumerate(vertices):
        x, y, z = (float(component) for component in position)
        length = max(math.sqrt(x * x + y * y + z * z), 1e-9)
        x, y, z = x / length, y / length, z / length
        result[index, 0] = 0.5 + math.atan2(z, x) / (2.0 * math.pi)
        result[index, 1] = 0.5 - math.asin(max(-1.0, min(1.0, y))) / math.pi
    return result


def skybox_mesh_data() -> MeshData:
    """Return an inward-facing cube mesh with panorama UV coordinates."""
    base = cube_mesh()
    vertices = np.asarray(base.vertices, dtype="f4").copy()
    normals = np.empty_like(vertices)
    for index, position in enumerate(vertices):
        length = max(float(np.linalg.norm(position)), 1e-9)
        normals[index] = -position / length
    return MeshData(vertices, normals, _equirectangular_uvs(vertices))


class Skybox3D(Mesh3D):
    """Camera-centered equirectangular skybox rendered through the normal mesh path.

    Call :meth:`follow` from the update loop so the box remains centered on the active camera.
    Lighting is disabled on the material; the panorama is displayed through ambient contribution.
    """

    def __init__(
        self,
        texture: str | Path,
        *,
        size: float = 80.0,
        tint: Color | None = None,
        name: str = "skybox",
        enabled: bool = True,
        visible: bool = True,
    ) -> None:
        size = float(size)
        if size <= 0.0:
            raise ValueError("skybox size must be greater than 0")
        material = Material3D(
            texture=texture,
            tint=tint or Color(),
            ambient=1.0,
            diffuse=0.0,
            specular=0.0,
        )
        super().__init__(
            skybox_mesh_data(),
            scale=Vec3(size, size, size),
            material=material,
            enabled=enabled,
            visible=visible,
            name=name,
            tags={"environment", "skybox"},
        )

    def follow(self, camera: Camera3D) -> None:
        self.position = Vec3(
            float(camera.position.x),
            float(camera.position.y),
            float(camera.position.z),
        )


@dataclass(slots=True)
class EnvironmentInstallation:
    """Objects installed into a scene by :class:`Environment3D`."""

    scene: Scene
    lights: tuple[DirectionalLight3D, ...]
    skybox: Skybox3D | None = None

    @property
    def objects(self) -> tuple[object, ...]:
        if self.skybox is None:
            return self.lights
        return (*self.lights, self.skybox)

    def remove(self) -> None:
        for obj in self.objects:
            self.scene.remove(obj)

    def follow(self, camera: Camera3D) -> None:
        if self.skybox is not None:
            self.skybox.follow(camera)


@dataclass(slots=True)
class Environment3D:
    """Creator-facing sky/ground environment lighting rig.

    The initial implementation deliberately uses two broad directional fill lights so it works
    with the existing OpenGL 3.3 forward renderer and leaves two directional-light slots free for
    authored sun/moon lights. The public object is designed to remain stable when true IBL lands.
    """

    sky_color: Color = field(default_factory=lambda: Color(0.48, 0.62, 1.0, 1.0))
    ground_color: Color = field(default_factory=lambda: Color(0.18, 0.16, 0.14, 1.0))
    intensity: float = 0.35
    ground_intensity: float = 0.16
    enabled: bool = True
    name: str = "environment"

    def __post_init__(self) -> None:
        self.intensity = max(0.0, float(self.intensity))
        self.ground_intensity = max(0.0, float(self.ground_intensity))

    def lights(self) -> tuple[DirectionalLight3D, DirectionalLight3D]:
        return (
            DirectionalLight3D(
                direction=Vec3(0.0, -1.0, 0.0),
                color=_scaled_rgb(self.sky_color.clamped(), self.intensity),
                intensity=1.0,
                enabled=self.enabled,
                name=f"{self.name}:sky",
                tags={"environment", "environment-light"},
            ),
            DirectionalLight3D(
                direction=Vec3(0.0, 1.0, 0.0),
                color=_scaled_rgb(self.ground_color.clamped(), self.ground_intensity),
                intensity=1.0,
                enabled=self.enabled,
                name=f"{self.name}:ground",
                tags={"environment", "environment-light"},
            ),
        )

    def install(
        self,
        scene: Scene,
        *,
        skybox_texture: str | Path | None = None,
        skybox_size: float = 80.0,
        skybox_tint: Color | None = None,
    ) -> EnvironmentInstallation:
        lights = self.lights()
        scene.add_many(*lights)
        skybox = None
        if skybox_texture is not None:
            skybox = Skybox3D(
                skybox_texture,
                size=skybox_size,
                tint=skybox_tint,
                name=f"{self.name}:skybox",
                enabled=self.enabled,
            )
            scene.add(skybox)
        return EnvironmentInstallation(scene=scene, lights=lights, skybox=skybox)
