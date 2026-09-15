from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from .graphics.animation import SpriteSheet
from .graphics.primitives import Sprite2D


@dataclass(slots=True)
class TileMapDiagnostics:
    """Creator-visible counters for tilemap CPU/render work."""

    transform_syncs: int = 0
    transform_sprite_visits: int = 0
    visibility_queries: int = 0
    last_visibility_candidates: int = 0
    last_visible_sprites: int = 0

    def reset(self) -> None:
        self.transform_syncs = 0
        self.transform_sprite_visits = 0
        self.visibility_queries = 0
        self.last_visibility_candidates = 0
        self.last_visible_sprites = 0


@dataclass(slots=True)
class TileMap2D:
    """Mutable grid backed by a fixed pool of Sprite2D cells.

    The fixed child pool remains available for 1.x compatibility, but SwirEngine 1.3 treats the
    tilemap as one aggregate update/render root. Unchanged transforms no longer walk the full pool
    every frame, and the renderer can request only cells overlapping the camera viewport.
    """

    texture: str | Path
    width: int
    height: int
    tile_width: float
    tile_height: float
    atlas_columns: int
    atlas_rows: int
    x: float = 0.0
    y: float = 0.0
    layer: int = 0
    enabled: bool = True
    visible: bool = True
    name: str = ""
    tags: set[str] = field(default_factory=set)
    diagnostics: TileMapDiagnostics = field(default_factory=TileMapDiagnostics, init=False)
    _tiles: list[int | None] = field(init=False, repr=False)
    _sprites: list[Sprite2D] = field(init=False, repr=False)
    _children: tuple[Sprite2D, ...] = field(init=False, repr=False)
    _sheet: SpriteSheet = field(init=False, repr=False)
    _tile_count_value: int = field(init=False, default=0, repr=False)
    _last_transform_state: tuple[float, float, int, bool, bool] | None = field(
        init=False,
        default=None,
        repr=False,
    )

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("tilemap width and height must be greater than zero")
        if self.tile_width <= 0 or self.tile_height <= 0:
            raise ValueError("tile size must be greater than zero")
        if self.atlas_columns <= 0 or self.atlas_rows <= 0:
            raise ValueError("atlas columns and rows must be greater than zero")
        self._sheet = SpriteSheet(self.atlas_columns, self.atlas_rows)
        self._tiles = [None] * (self.width * self.height)
        self._sprites = []
        owner_id = id(self)
        for row in range(self.height):
            for column in range(self.width):
                sprite = Sprite2D(
                    self.texture,
                    width=self.tile_width,
                    height=self.tile_height,
                    visible=False,
                    layer=self.layer,
                    name=self._cell_name(column, row),
                )
                sprite._render_owner_id = owner_id
                self._sprites.append(sprite)
        self._children = tuple(self._sprites)
        self._sync_transforms(force=True)

    @property
    def children(self) -> tuple[Sprite2D, ...]:
        return self._children

    @property
    def tile_count(self) -> int:
        return self._tile_count_value

    @property
    def render_managed(self) -> bool:
        return False

    @property
    def update_managed(self) -> bool:
        return False

    def _index(self, column: int, row: int) -> int:
        if not 0 <= column < self.width or not 0 <= row < self.height:
            raise IndexError("tilemap cell is out of range")
        return row * self.width + column

    def _cell_name(self, column: int, row: int) -> str:
        prefix = self.name or "tilemap"
        return f"{prefix}[{column},{row}]"

    def _transform_state(self) -> tuple[float, float, int, bool, bool]:
        return (float(self.x), float(self.y), int(self.layer), bool(self.enabled), bool(self.visible))

    def _sync_transforms(self, *, force: bool = False) -> int:
        state = self._transform_state()
        if not force and state == self._last_transform_state:
            return 0
        origin_x, origin_y, layer, enabled, visible = state
        for index, sprite in enumerate(self._sprites):
            row, column = divmod(index, self.width)
            sprite.x = origin_x + (column + 0.5) * self.tile_width
            sprite.y = origin_y + (row + 0.5) * self.tile_height
            sprite.layer = layer
            sprite.enabled = enabled
            sprite.visible = visible and self._tiles[index] is not None
        visits = len(self._sprites)
        self._last_transform_state = state
        self.diagnostics.transform_syncs += 1
        self.diagnostics.transform_sprite_visits += visits
        return visits

    def get_tile(self, column: int, row: int) -> int | None:
        return self._tiles[self._index(column, row)]

    def set_tile(self, column: int, row: int, tile: int | None) -> TileMap2D:
        index = self._index(column, row)
        if tile is not None:
            tile = int(tile)
            max_tiles = self.atlas_columns * self.atlas_rows
            if not 0 <= tile < max_tiles:
                raise IndexError("tile atlas index is out of range")
        previous = self._tiles[index]
        if previous is None and tile is not None:
            self._tile_count_value += 1
        elif previous is not None and tile is None:
            self._tile_count_value -= 1
        self._tiles[index] = tile
        sprite = self._sprites[index]
        sprite.visible = self.visible and tile is not None
        if tile is not None:
            atlas_row, atlas_column = divmod(tile, self.atlas_columns)
            sprite.uv_rect = self._sheet.frame(atlas_column, atlas_row)
        return self

    def fill(self, tile: int | None) -> TileMap2D:
        for row in range(self.height):
            for column in range(self.width):
                self.set_tile(column, row, tile)
        return self

    def clear(self) -> TileMap2D:
        return self.fill(None)

    def load_rows(
        self,
        rows: list[list[int | None]] | tuple[tuple[int | None, ...], ...],
    ) -> TileMap2D:
        if len(rows) != self.height or any(len(row) != self.width for row in rows):
            raise ValueError("tile data dimensions must match the tilemap")
        for row_index, row in enumerate(rows):
            for column, tile in enumerate(row):
                self.set_tile(column, row_index, tile)
        return self

    def world_to_cell(self, x: float, y: float) -> tuple[int, int]:
        column = int((x - self.x) // self.tile_width)
        row = int((y - self.y) // self.tile_height)
        return column, row

    def cell_to_world(self, column: int, row: int) -> tuple[float, float]:
        self._index(column, row)
        return (
            self.x + (column + 0.5) * self.tile_width,
            self.y + (row + 0.5) * self.tile_height,
        )

    def visible_cell_bounds(
        self,
        camera_x: float,
        camera_y: float,
        viewport_width: float,
        viewport_height: float,
        *,
        zoom: float = 1.0,
    ) -> tuple[int, int, int, int]:
        """Return clamped ``(column_start, row_start, column_stop, row_stop)`` bounds."""
        safe_zoom = max(0.000001, float(zoom))
        half_width = max(0.0, float(viewport_width)) / (2.0 * safe_zoom)
        half_height = max(0.0, float(viewport_height)) / (2.0 * safe_zoom)
        left = float(camera_x) - half_width
        right = float(camera_x) + half_width
        bottom = float(camera_y) - half_height
        top = float(camera_y) + half_height

        column_start = max(0, math.floor((left - self.x) / self.tile_width))
        row_start = max(0, math.floor((bottom - self.y) / self.tile_height))
        column_stop = min(self.width, math.ceil((right - self.x) / self.tile_width))
        row_stop = min(self.height, math.ceil((top - self.y) / self.tile_height))
        column_stop = max(column_start, column_stop)
        row_stop = max(row_start, row_stop)
        return column_start, row_start, column_stop, row_stop

    def iter_visible_sprites(
        self,
        camera_x: float,
        camera_y: float,
        viewport_width: float,
        viewport_height: float,
        *,
        zoom: float = 1.0,
    ) -> Iterator[Sprite2D]:
        """Yield only live cells overlapping the current world-space viewport."""
        self._sync_transforms()
        self.diagnostics.visibility_queries += 1
        if not self.enabled or not self.visible:
            self.diagnostics.last_visibility_candidates = 0
            self.diagnostics.last_visible_sprites = 0
            return

        column_start, row_start, column_stop, row_stop = self.visible_cell_bounds(
            camera_x,
            camera_y,
            viewport_width,
            viewport_height,
            zoom=zoom,
        )
        candidates = max(0, column_stop - column_start) * max(0, row_stop - row_start)
        self.diagnostics.last_visibility_candidates = candidates
        visible_count = 0
        for row in range(row_start, row_stop):
            row_offset = row * self.width
            for column in range(column_start, column_stop):
                index = row_offset + column
                if self._tiles[index] is None:
                    continue
                sprite = self._sprites[index]
                if sprite.enabled and sprite.visible:
                    visible_count += 1
                    yield sprite
        self.diagnostics.last_visible_sprites = visible_count

    def update(self, dt: float) -> None:
        del dt
        self._sync_transforms()
