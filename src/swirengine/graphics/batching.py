from __future__ import annotations

from collections.abc import Iterable, Iterator
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


@lru_cache(maxsize=8192)
def _cached_sprite_batch_key(texture: str, layer: int, screen_space: bool) -> SpriteBatchKey:
    """Reuse immutable state keys instead of allocating one per sprite on every frame."""
    return SpriteBatchKey(texture=texture, layer=layer, screen_space=screen_space)


def sprite_batch_key(sprite: Sprite2D) -> SpriteBatchKey:
    return _cached_sprite_batch_key(
        _canonical_texture_key(str(sprite.texture)),
        int(sprite.layer),
        bool(sprite.screen_space),
    )


def iter_render_runs(objects: Iterable[object]) -> Iterator[object | SpriteBatch]:
    """Yield visible render runs in order without materializing an outer frame tuple.

    The renderer can consume this hot-path iterator directly. Only the currently pending
    compatible sprite run is retained, so scenes with many rectangles/text objects do not
    need a second frame-sized list/tuple merely to iterate it once.
    """
    renderable_types = (Rectangle2D, Sprite2D, Text2D)
    pending_key: SpriteBatchKey | None = None
    pending_sprites: list[Sprite2D] = []

    for obj in objects:
        if (
            not isinstance(obj, renderable_types)
            or not getattr(obj, "enabled", True)
            or not getattr(obj, "visible", True)
        ):
            continue

        if isinstance(obj, Sprite2D):
            key = sprite_batch_key(obj)
            if pending_key is key or pending_key == key:
                pending_sprites.append(obj)
                continue
            if pending_key is not None:
                yield SpriteBatch(pending_key, tuple(pending_sprites))
                pending_sprites.clear()
            pending_key = key
            pending_sprites.append(obj)
            continue

        if pending_key is not None:
            yield SpriteBatch(pending_key, tuple(pending_sprites))
            pending_sprites.clear()
            pending_key = None
        yield obj

    if pending_key is not None:
        yield SpriteBatch(pending_key, tuple(pending_sprites))


def build_render_runs(objects: Iterable[object]) -> tuple[object | SpriteBatch, ...]:
    """Compatibility wrapper returning the historical materialized tuple of render runs."""
    return tuple(iter_render_runs(objects))
