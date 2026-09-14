from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import overload

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
    """Yield visible render runs while retaining only the pending sprite batch."""
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


class RenderRuns(Sequence[object | SpriteBatch]):
    """Sequence-compatible render-run view with a zero-materialization iteration fast path.

    Repeatable inputs such as the renderer's sorted scene list stream directly on iteration,
    avoiding a second frame-sized list/tuple. One-shot iterators are materialized once so the
    historical indexing/length behavior remains deterministic for callers that need it.
    """

    __slots__ = ("_cache", "_objects", "_single_pass")

    def __init__(self, objects: Iterable[object]) -> None:
        self._objects = objects
        self._single_pass = iter(objects) is objects
        self._cache: tuple[object | SpriteBatch, ...] | None = None

    def _materialize(self) -> tuple[object | SpriteBatch, ...]:
        if self._cache is None:
            self._cache = tuple(iter_render_runs(self._objects))
        return self._cache

    def __iter__(self) -> Iterator[object | SpriteBatch]:
        if self._cache is not None:
            return iter(self._cache)
        if self._single_pass:
            return iter(self._materialize())
        return iter_render_runs(self._objects)

    def __len__(self) -> int:
        return len(self._materialize())

    @overload
    def __getitem__(self, index: int) -> object | SpriteBatch: ...

    @overload
    def __getitem__(self, index: slice) -> tuple[object | SpriteBatch, ...]: ...

    def __getitem__(
        self,
        index: int | slice,
    ) -> object | SpriteBatch | tuple[object | SpriteBatch, ...]:
        return self._materialize()[index]

    def __repr__(self) -> str:
        return repr(self._materialize())

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Sequence):
            return tuple(self) == tuple(other)
        return NotImplemented


def build_render_runs(objects: Iterable[object]) -> RenderRuns:
    """Build an order-preserving sequence view of visible render runs.

    Existing callers keep sequence semantics (iteration, ``len`` and indexing), while the
    renderer's ordinary repeatable list input no longer creates an outer run tuple per frame.
    """
    return RenderRuns(objects)
