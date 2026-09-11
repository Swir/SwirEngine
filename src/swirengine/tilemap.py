from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .graphics.animation import SpriteSheet
from .graphics.primitives import Sprite2D


@dataclass(slots=True)
class TileMap2D:
    """Mutable grid backed by a fixed pool of Sprite2D cells."""

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
    _tiles: list[int | None] = field(init=False, repr=False)
    _sprites: list[Sprite2D] = field(init=False, repr=False)
    _sheet: SpriteSheet = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("tilemap width and height must be greater than zero")
        if self.tile_width <= 0 or self.tile_height <= 0:
            raise ValueError("tile size must be greater than zero")
        self._sheet = SpriteSheet(self.atlas_columns, self.atlas_rows)
        self._tiles = [None] * (self.width * self.height)
        self._sprites = []
        for row in range(self.height):
            for column in range(self.width):
                self._sprites.append(
                    Sprite2D(
                        self.texture,
                        width=self.tile_width,
                        height=self.tile_height,
                        visible=False,
                        layer=self.layer,
                        name=self._cell_name(column, row),
                    )
                )
        self._sync_transforms()

    @property
    def children(self) -> tuple[Sprite2D, ...]:
        return tuple(self._sprites)

    @property
    def tile_count(self) -> int:
        return sum(tile is not None for tile in self._tiles)

    def _index(self, column: int, row: int) -> int:
        if not 0 <= column < self.width or not 0 <= row < self.height:
            raise IndexError("tilemap cell is out of range")
        return row * self.width + column

    def _cell_name(self, column: int, row: int) -> str:
        prefix = self.name or "tilemap"
        return f"{prefix}[{column},{row}]"

    def _sync_transforms(self) -> None:
        for row in range(self.height):
            for column in range(self.width):
                sprite = self._sprites[row * self.width + column]
                sprite.x = self.x + (column + 0.5) * self.tile_width
                sprite.y = self.y + (row + 0.5) * self.tile_height
                sprite.layer = self.layer
                sprite.enabled = self.enabled
                sprite.visible = self.visible and self._tiles[row * self.width + column] is not None

    def get_tile(self, column: int, row: int) -> int | None:
        return self._tiles[self._index(column, row)]

    def set_tile(self, column: int, row: int, tile: int | None) -> TileMap2D:
        index = self._index(column, row)
        if tile is not None:
            tile = int(tile)
            max_tiles = self.atlas_columns * self.atlas_rows
            if not 0 <= tile < max_tiles:
                raise IndexError("tile atlas index is out of range")
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

    def update(self, dt: float) -> None:
        del dt
        self._sync_transforms()
