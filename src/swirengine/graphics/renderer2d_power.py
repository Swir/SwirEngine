from __future__ import annotations

import math
from collections.abc import Iterable, Iterator
from typing import Protocol

import numpy as np

from ..math.types import orthographic
from ..tilemap import TileMap2D
from .batching import SpriteBatch, iter_render_runs
from .camera import Camera2D
from .primitives import Rectangle2D, Sprite2D, Text2D

_SPRITE_VERTICES = (
    (-0.5, -0.5, 0.0, 0.0),
    (0.5, -0.5, 1.0, 0.0),
    (0.5, 0.5, 1.0, 1.0),
    (-0.5, -0.5, 0.0, 0.0),
    (0.5, 0.5, 1.0, 1.0),
    (-0.5, 0.5, 0.0, 1.0),
)


class Renderer2DHost(Protocol):
    ctx: object
    width: int
    height: int
    stats: object
    program2d: object
    sprite_program: object
    sprite_batch_program: object
    sprite_batch_vbo: object
    sprite_batch_vao: object
    sprite_vao: object
    vao2d: object

    def _texture(self, path: object) -> tuple[object, int, int]: ...

    def _text_texture(self, obj: Text2D) -> tuple[object, int, int]: ...

    def _ensure_sprite_batch_capacity(self, count: int) -> None: ...

    @staticmethod
    def _write_mat4(uniform: object, matrix: np.ndarray) -> None: ...

    @staticmethod
    def _center(
        obj: Rectangle2D | Sprite2D | Text2D,
        camera: Camera2D,
    ) -> tuple[float, float]: ...


class Renderer2DPowerPass:
    """Reusable 2D hot-path state attached to the production renderer.

    The staging array grows geometrically and is reused across frames. Tilemaps remain compatible
    fixed child pools, but their managed sprites are expanded only for cells intersecting the
    camera viewport instead of entering the scene-wide render sort individually.
    """

    def __init__(self, *, initial_sprite_capacity: int = 256) -> None:
        capacity = max(1, int(initial_sprite_capacity))
        self._sprite_capacity = capacity
        self._sprite_staging = np.empty((capacity * 6, 8), dtype="f4")
        self.staging_reallocations = 0

    @property
    def sprite_capacity(self) -> int:
        return self._sprite_capacity

    @property
    def staging_identity(self) -> int:
        return id(self._sprite_staging)

    def _ensure_staging_capacity(self, count: int) -> None:
        if count <= self._sprite_capacity:
            return
        capacity = self._sprite_capacity
        while capacity < count:
            capacity *= 2
        self._sprite_capacity = capacity
        self._sprite_staging = np.empty((capacity * 6, 8), dtype="f4")
        self.staging_reallocations += 1

    @staticmethod
    def _is_in_view(
        host: Renderer2DHost,
        obj: object,
        camera: Camera2D,
    ) -> bool:
        if not getattr(obj, "enabled", True) or not getattr(obj, "visible", True):
            return False
        if getattr(obj, "screen_space", False):
            return True

        if isinstance(obj, Rectangle2D):
            width = abs(float(obj.width))
            height = abs(float(obj.height))
        elif isinstance(obj, Sprite2D) and obj.width is not None and obj.height is not None:
            width = abs(float(obj.width))
            height = abs(float(obj.height))
        else:
            return True

        radius = 0.5 * math.hypot(width, height)
        half_width = host.width / (2.0 * camera.safe_zoom)
        half_height = host.height / (2.0 * camera.safe_zoom)
        x = float(getattr(obj, "x", 0.0))
        y = float(getattr(obj, "y", 0.0))
        return not (
            x + radius < camera.x - half_width
            or x - radius > camera.x + half_width
            or y + radius < camera.y - half_height
            or y - radius > camera.y + half_height
        )

    def iter_renderables(
        self,
        host: Renderer2DHost,
        roots: Iterable[object],
        camera: Camera2D,
    ) -> Iterator[object]:
        for obj in roots:
            if isinstance(obj, TileMap2D):
                if not obj.enabled or not obj.visible:
                    continue
                for sprite in obj.iter_visible_sprites(
                    camera.x,
                    camera.y,
                    host.width,
                    host.height,
                    zoom=camera.safe_zoom,
                ):
                    yield sprite
                host.stats.tilemap_cells_considered += (  # type: ignore[attr-defined]
                    obj.diagnostics.last_visibility_candidates
                )
                host.stats.tilemap_cells_visible += (  # type: ignore[attr-defined]
                    obj.diagnostics.last_visible_sprites
                )
                continue

            if self._is_in_view(host, obj, camera):
                yield obj
            elif getattr(obj, "enabled", True) and getattr(obj, "visible", True):
                host.stats.objects_culled_2d += 1  # type: ignore[attr-defined]

    def _sprite_vertices(
        self,
        host: Renderer2DHost,
        batch: SpriteBatch,
        image_width: int,
        image_height: int,
        camera: Camera2D,
    ) -> np.ndarray:
        count = len(batch.sprites)
        self._ensure_staging_capacity(count)
        staging = self._sprite_staging
        cursor = 0
        for sprite in batch.sprites:
            width = float(sprite.width if sprite.width is not None else image_width)
            height = float(sprite.height if sprite.height is not None else image_height)
            center_x, center_y = host._center(sprite, camera)
            angle = math.radians(float(sprite.rotation))
            cos_angle, sin_angle = math.cos(angle), math.sin(angle)
            u0, v0, u1, v1 = map(float, sprite.uv_rect)
            tint = sprite.tint.clamped()
            tint_r, tint_g, tint_b, tint_a = tint.r, tint.g, tint.b, tint.a

            for local_x, local_y, unit_u, unit_v in _SPRITE_VERTICES:
                scaled_x = local_x * width
                scaled_y = local_y * height
                row = staging[cursor]
                row[0] = cos_angle * scaled_x - sin_angle * scaled_y + center_x
                row[1] = sin_angle * scaled_x + cos_angle * scaled_y + center_y
                row[2] = u0 + (u1 - u0) * unit_u
                row[3] = v0 + (v1 - v0) * unit_v
                row[4] = tint_r
                row[5] = tint_g
                row[6] = tint_b
                row[7] = tint_a
                cursor += 1
        return staging[: count * 6]

    def render_sprite_batch(
        self,
        host: Renderer2DHost,
        batch: SpriteBatch,
        camera: Camera2D,
        projection: np.ndarray,
        screen_projection: np.ndarray,
    ) -> None:
        texture, image_width, image_height = host._texture(batch.key.texture)
        current = screen_projection if batch.key.screen_space else projection
        vertices = self._sprite_vertices(host, batch, image_width, image_height, camera)
        count = len(batch.sprites)
        host._ensure_sprite_batch_capacity(count)
        host.sprite_batch_vbo.write(memoryview(vertices))  # type: ignore[attr-defined]
        host._write_mat4(host.sprite_batch_program["projection"], current)  # type: ignore[index]
        texture.use(location=0)  # type: ignore[attr-defined]
        host.sprite_batch_vao.render(vertices=count * 6)  # type: ignore[attr-defined]
        host.stats.draw_calls += 1  # type: ignore[attr-defined]
        host.stats.sprites += count  # type: ignore[attr-defined]
        host.stats.sprite_batches += 1  # type: ignore[attr-defined]
        host.stats.triangles += count * 2  # type: ignore[attr-defined]

    def render(self, host: Renderer2DHost, scene: object, camera: Camera2D) -> None:
        host.ctx.enable(host.ctx.BLEND)  # type: ignore[attr-defined]
        host.ctx.blend_func = (  # type: ignore[attr-defined]
            host.ctx.SRC_ALPHA,  # type: ignore[attr-defined]
            host.ctx.ONE_MINUS_SRC_ALPHA,  # type: ignore[attr-defined]
        )
        projection = orthographic(
            host.width / camera.safe_zoom,
            host.height / camera.safe_zoom,
        )
        screen_projection = orthographic(host.width, host.height)
        roots = getattr(scene, "render_objects", None)
        if roots is None:
            roots = getattr(scene, "objects", ())
        host.stats.render_roots_2d = len(roots)  # type: ignore[attr-defined]
        ordered = sorted(roots, key=lambda item: getattr(item, "layer", 0))
        renderables = self.iter_renderables(host, ordered, camera)

        for item in iter_render_runs(renderables):
            if isinstance(item, SpriteBatch):
                self.render_sprite_batch(host, item, camera, projection, screen_projection)
                continue
            obj = item
            current = screen_projection if obj.screen_space else projection
            if isinstance(obj, Rectangle2D):
                host._write_mat4(host.program2d["projection"], current)  # type: ignore[index]
                host.program2d["center"].value = host._center(obj, camera)  # type: ignore[index]
                host.program2d["size"].value = (float(obj.width), float(obj.height))  # type: ignore[index]
                host.program2d["angle"].value = math.radians(float(obj.rotation))  # type: ignore[index]
                color = obj.color.clamped()
                host.program2d["color"].value = (  # type: ignore[index]
                    color.r,
                    color.g,
                    color.b,
                    color.a,
                )
                host.vao2d.render()  # type: ignore[attr-defined]
                host.stats.draw_calls += 1  # type: ignore[attr-defined]
                host.stats.rectangles += 1  # type: ignore[attr-defined]
                host.stats.triangles += 2  # type: ignore[attr-defined]
            elif isinstance(obj, Text2D):
                texture, width, height = host._text_texture(obj)
                host._write_mat4(host.sprite_program["projection"], current)  # type: ignore[index]
                host.sprite_program["center"].value = host._center(obj, camera)  # type: ignore[index]
                host.sprite_program["size"].value = (  # type: ignore[index]
                    width * obj.scale,
                    height * obj.scale,
                )
                host.sprite_program["angle"].value = 0.0  # type: ignore[index]
                color = obj.color.clamped()
                host.sprite_program["tint"].value = (  # type: ignore[index]
                    color.r,
                    color.g,
                    color.b,
                    color.a,
                )
                host.sprite_program["uv_rect"].value = (0.0, 0.0, 1.0, 1.0)  # type: ignore[index]
                texture.use(location=0)  # type: ignore[attr-defined]
                host.sprite_vao.render()  # type: ignore[attr-defined]
                host.stats.draw_calls += 1  # type: ignore[attr-defined]
                host.stats.texts += 1  # type: ignore[attr-defined]
                host.stats.triangles += 2  # type: ignore[attr-defined]
        host.ctx.disable(host.ctx.BLEND)  # type: ignore[attr-defined]
