from __future__ import annotations

from .core.scene import Scene
from .graphics.primitives import Text2D
from .math.types import Color
from .profiler import Profiler


class DebugOverlay:
    """Small screen-space profiler overlay that works with the normal text renderer."""

    def __init__(
        self,
        scene: Scene,
        profiler: Profiler,
        *,
        refresh_hz: float = 4.0,
        layer: int = 1_000_000,
    ) -> None:
        self.profiler = profiler
        self.refresh_hz = max(0.5, float(refresh_hz))
        self.enabled = False
        self._elapsed = 0.0
        color = Color(0.85, 0.95, 1.0, 1.0)
        self._lines = tuple(
            Text2D(
                "",
                font_size=15,
                color=color,
                screen_space=True,
                layer=layer + index,
                visible=False,
                name=f"__swir_debug_{index}",
            )
            for index in range(3)
        )
        scene.add_many(*self._lines)

    @property
    def children(self) -> tuple[Text2D, ...]:
        return self._lines

    def set_enabled(self, enabled: bool = True) -> DebugOverlay:
        self.enabled = bool(enabled)
        for line in self._lines:
            line.visible = self.enabled
        return self

    def toggle(self) -> bool:
        self.set_enabled(not self.enabled)
        return self.enabled

    def update(self, dt: float, width: int, height: int) -> None:
        if not self.enabled:
            return

        left = -max(1, int(width)) / 2.0
        top = max(1, int(height)) / 2.0
        for index, line in enumerate(self._lines):
            line.x = left + 180.0
            line.y = top - 20.0 - index * 20.0

        self._elapsed += max(0.0, float(dt))
        interval = 1.0 / self.refresh_hz
        if self._elapsed < interval:
            return
        self._elapsed %= interval

        profile = self.profiler.average(min(30, len(self.profiler.samples)))
        self._lines[0].text = (
            f"FPS {profile.fps:6.1f} | frame {profile.frame_ms:6.2f} ms | "
            f"CPU {profile.cpu_ms:6.2f} ms"
        )
        self._lines[1].text = (
            f"update {profile.update_ms:5.2f} | physics {profile.physics_ms:5.2f} | "
            f"render {profile.render_ms:5.2f} ms"
        )
        self._lines[2].text = (
            f"draw {profile.draw_calls} | sprites {profile.sprites} | "
            f"batches {profile.sprite_batches} | tris {profile.triangles}"
        )
