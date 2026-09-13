from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .primitives import Rectangle2D, Sprite2D, Text2D


@dataclass(frozen=True, slots=True)
class SpriteBatchKey:
    texture: str
    layer: int
    screen_space: bool


@dataclass(frozen=True, slots=True)
class SpriteBatch:
    key: SpriteBatchKey
    sprites: tuple[Sprite2D, ...]


@lru_cache(maxsize=4096)
def _canonical_texture_key(texture: str) -> str:
    """Resolve a texture path once and reuse it across subsequent frames."""
    return str(Path(texture).expanduser().resolve())


def sprite_batch_key(sprite: Sprite2D) -> SpriteBatchKey:
    return SpriteBatchKey(
        texture=_canonical_texture_key(str(sprite.texture)),
        layer=int(sprite.layer),
        screen_space=bool(sprite.screen_space),
    )


def build_render_runs(objects: Iterable[object]) -> tuple[object | SpriteBatch, ...]:
    """Preserve visible render order while merging adjacent compatible sprites.

    The implementation is deliberately single-pass. It avoids building a second visible-object
    tuple and computes each sprite's canonical texture key at most once per pass. Combined with
    the bounded path cache this removes filesystem path normalization from the steady-state frame
    loop for unchanged assets.
    """
    renderable_types = (Rectangle2D, Sprite2D, Text2D)
    runs: list[object | SpriteBatch] = []
    pending_key: SpriteBatchKey | None = None
    pending_sprites: list[Sprite2D] = []

    def flush_sprites() -> None:
        nonlocal pending_key
        if pending_key is None:
            return
        runs.append(SpriteBatch(pending_key, tuple(pending_sprites)))
        pending_sprites.clear()
        pending_key = None

    for obj in objects:
        if (
            not isinstance(obj, renderable_types)
            or not getattr(obj, "enabled", True)
            or not getattr(obj, "visible", True)
        ):
            continue

        if isinstance(obj, Sprite2D):
            key = sprite_batch_key(obj)
            if pending_key == key:
                pending_sprites.append(obj)
                continue
            flush_sprites()
            pending_key = key
            pending_sprites.append(obj)
            continue

        flush_sprites()
        runs.append(obj)

    flush_sprites()
    return tuple(runs)
