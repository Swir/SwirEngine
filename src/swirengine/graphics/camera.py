from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Camera2D:
    x: float = 0.0
    y: float = 0.0
    zoom: float = 1.0

    def move(self, dx: float, dy: float) -> "Camera2D":
        self.x += dx
        self.y += dy
        return self

    def look_at(self, x: float, y: float) -> "Camera2D":
        self.x = x
        self.y = y
        return self

    def follow(self, target: object) -> "Camera2D":
        self.x = float(getattr(target, "x"))
        self.y = float(getattr(target, "y"))
        return self

    @property
    def safe_zoom(self) -> float:
        return max(0.001, float(self.zoom))
