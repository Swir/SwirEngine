from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .primitives import Sprite2D

UVRect = tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class AnimationClip:
    frames: tuple[UVRect, ...]
    fps: float = 12.0
    loop: bool = True

    def __post_init__(self) -> None:
        if not self.frames:
            raise ValueError("animation clip requires at least one frame")
        if self.fps <= 0:
            raise ValueError("animation fps must be greater than zero")


@dataclass(frozen=True, slots=True)
class SpriteSheet:
    columns: int
    rows: int

    def __post_init__(self) -> None:
        if self.columns <= 0 or self.rows <= 0:
            raise ValueError("sprite sheet rows and columns must be greater than zero")

    def frame(self, column: int, row: int) -> UVRect:
        if not 0 <= column < self.columns:
            raise IndexError("sprite sheet column is out of range")
        if not 0 <= row < self.rows:
            raise IndexError("sprite sheet row is out of range")

        u0 = column / self.columns
        u1 = (column + 1) / self.columns
        v0 = 1.0 - (row + 1) / self.rows
        v1 = 1.0 - row / self.rows
        return (u0, v0, u1, v1)

    def row(self, row: int, *, start: int = 0, count: int | None = None) -> tuple[UVRect, ...]:
        if count is None:
            count = self.columns - start
        if start < 0 or count < 0 or start + count > self.columns:
            raise IndexError("sprite sheet row slice is out of range")
        return tuple(self.frame(column, row) for column in range(start, start + count))


@dataclass(slots=True)
class AnimatedSprite2D(Sprite2D):
    """Sprite with named frame animations that advances automatically in ``Scene.update``."""

    animations: dict[str, AnimationClip] = field(default_factory=dict, init=False, repr=False)
    animation: str | None = field(default=None, init=False)
    frame_index: int = field(default=0, init=False)
    playing: bool = field(default=False, init=False)
    _elapsed: float = field(default=0.0, init=False, repr=False)

    def add_animation(
        self,
        name: str,
        frames: tuple[UVRect, ...] | list[UVRect],
        *,
        fps: float = 12.0,
        loop: bool = True,
    ) -> AnimatedSprite2D:
        if not name:
            raise ValueError("animation name cannot be empty")
        clip = AnimationClip(tuple(frames), float(fps), bool(loop))
        self.animations[name] = clip
        if self.animation is None:
            self.play(name)
        return self

    def play(self, name: str, *, restart: bool = False) -> AnimatedSprite2D:
        if name not in self.animations:
            raise KeyError(f"unknown animation: {name}")
        if restart or self.animation != name:
            self.animation = name
            self.frame_index = 0
            self._elapsed = 0.0
            self.uv_rect = self.animations[name].frames[0]
        self.playing = True
        return self

    def pause(self) -> AnimatedSprite2D:
        self.playing = False
        return self

    def stop(self) -> AnimatedSprite2D:
        self.playing = False
        self.frame_index = 0
        self._elapsed = 0.0
        if self.animation is not None:
            self.uv_rect = self.animations[self.animation].frames[0]
        return self

    def update(self, dt: float) -> None:
        if not self.playing or self.animation is None or dt <= 0:
            return

        clip = self.animations[self.animation]
        self._elapsed += dt
        frame_duration = 1.0 / clip.fps
        while self._elapsed >= frame_duration:
            self._elapsed -= frame_duration
            next_frame = self.frame_index + 1
            if next_frame >= len(clip.frames):
                if clip.loop:
                    next_frame = 0
                else:
                    next_frame = len(clip.frames) - 1
                    self.playing = False
            self.frame_index = next_frame
            self.uv_rect = clip.frames[self.frame_index]
            if not self.playing:
                break


def animated_sprite(
    texture: str | Path,
    sheet: SpriteSheet,
    *,
    row: int = 0,
    fps: float = 12.0,
    loop: bool = True,
    **kwargs: object,
) -> AnimatedSprite2D:
    """Convenience factory for a one-row sprite-sheet animation."""

    sprite = AnimatedSprite2D(texture, **kwargs)
    sprite.add_animation("default", sheet.row(row), fps=fps, loop=loop)
    return sprite
