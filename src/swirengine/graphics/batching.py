from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .primitives import Sprite2D


@dataclass(frozen=True, slots=True)
class SpriteBatchKey:
    texture: str
    layer: int
    screen_space: bool


@dataclass(frozen=True, slots=True)
class SpriteBatch:
    key: SpriteBatchKey
    sprites: tuple[Sprite2D, ...]


def sprite_batch_key(sprite: Sprite2D) -> SpriteBatchKey:
    return SpriteBatchKey(
        texture=str(Path(sprite.texture).expanduser().resolve()),
        layer=int(sprite.layer),
        screen_space=bool(sprite.screen_space),
    )


def build_render_runs(objects: Iterable[object]) -> tuple[object | SpriteBatch, ...]:
    """Preserve render order while merging adjacent compatible sprites."""
    visible = tuple(
        obj
        for obj in objects
        if getattr(obj, "enabled", True) and getattr(obj, "visible", True)
    )
    runs: list[object | SpriteBatch] = []
    index = 0
    while index < len(visible):
        obj = visible[index]
        if not isinstance(obj, Sprite2D):
            runs.append(obj)
            index += 1
            continue

        key = sprite_batch_key(obj)
        batch = [obj]
        index += 1
        while index < len(visible):
            candidate = visible[index]
            if not isinstance(candidate, Sprite2D) or sprite_batch_key(candidate) != key:
                break
            batch.append(candidate)
            index += 1
        runs.append(SpriteBatch(key, tuple(batch)))
    return tuple(runs)
