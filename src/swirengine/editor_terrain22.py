from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .terrain import TerrainConfig, TerrainMaterialLayer
from .terrain_authoring22 import (
    FoliagePlacement,
    TerrainAuthoringAsset,
    TerrainEditorSession,
    TerrainProjectStore,
)


class EditorTerrainError22(ValueError):
    """Raised when project terrain assets cannot be authored safely."""


@dataclass(frozen=True, slots=True)
class EditorTerrainSnapshot22:
    asset_paths: tuple[str, ...]
    selected: str | None
    dirty: bool


class EditorTerrainTooling22:
    """Project-scoped terrain documents integrated with the shipping terrain runtime."""

    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root).expanduser().resolve()
        self.store = TerrainProjectStore(self.project_root)
        self._documents: dict[str, TerrainEditorSession] = {}
        self._selected: str | None = None

    @property
    def dirty(self) -> bool:
        return any(document.dirty for document in self._documents.values())

    def snapshot(self) -> EditorTerrainSnapshot22:
        return EditorTerrainSnapshot22(self.asset_paths(), self._selected, self.dirty)

    def asset_paths(self) -> tuple[str, ...]:
        paths = set(self._documents)
        root = self.store.asset_root
        if root.is_dir():
            paths.update(
                path.relative_to(root).as_posix()
                for path in root.rglob("*.swirterrain")
                if path.is_file()
            )
        return tuple(sorted(paths))

    def create(
        self,
        asset_path: str | Path,
        *,
        width: int = 65,
        height: int = 65,
        value: float = 0.0,
        config: TerrainConfig | None = None,
    ) -> TerrainEditorSession:
        key = self._key(asset_path)
        target = self.store.resolve(key)
        if target.exists() or key in self._documents:
            raise EditorTerrainError22(f"terrain asset already exists: {key}")
        if min(width, height) < 2:
            raise EditorTerrainError22("terrain dimensions must be at least 2x2")
        layers = (TerrainMaterialLayer("ground"), TerrainMaterialLayer("detail"))
        splat = np.zeros((height, width, len(layers)), dtype="f4")
        splat[:, :, 0] = 1.0
        asset = TerrainAuthoringAsset(
            np.full((height, width), value, dtype="f4"),
            config=config or TerrainConfig(),
            layers=layers,
            splat=splat,
        )
        document = TerrainEditorSession.create(self.store, key, asset)
        self._documents[key] = document
        self._selected = key
        return document

    def open(self, asset_path: str | Path) -> TerrainEditorSession:
        key = self._key(asset_path)
        document = self._documents.get(key)
        if document is None:
            try:
                document = TerrainEditorSession.open(self.store, key)
            except FileNotFoundError as exc:
                raise EditorTerrainError22(f"terrain asset does not exist: {key}") from exc
            self._documents[key] = document
        self._selected = key
        return document

    def selected_document(self) -> TerrainEditorSession:
        if self._selected is None:
            raise EditorTerrainError22("no terrain asset is selected")
        return self._documents[self._selected]

    def save(self) -> tuple[Path, ...]:
        saved: list[Path] = []
        for key in sorted(self._documents):
            document = self._documents[key]
            if document.dirty:
                saved.append(document.save())
        return tuple(saved)

    def reload_selected(self) -> TerrainEditorSession:
        document = self.selected_document()
        if not document.project_path.is_file():
            raise EditorTerrainError22("cannot reload an unsaved terrain asset")
        document.reload()
        return document

    def _key(self, asset_path: str | Path) -> str:
        target = self.store.resolve(asset_path)
        return target.relative_to(self.store.asset_root).as_posix()


@dataclass(frozen=True, slots=True)
class TerrainRuntimePreview22:
    world_width: float
    world_depth: float
    chunks_x: int
    chunks_z: int
    lod_count: int
    active_radius_chunks: int
    preload_radius_chunks: int


class EditorTerrainPanelController22:
    """Toolkit-neutral terrain panel controller used by the unified SwirEditor shell."""

    def __init__(self, tooling: EditorTerrainTooling22) -> None:
        if not isinstance(tooling, EditorTerrainTooling22):
            raise TypeError("tooling must be EditorTerrainTooling22")
        self.tooling = tooling
        self._status = "World/Terrain authoring ready"

    @property
    def status(self) -> str:
        return self._status

    def snapshot(self) -> EditorTerrainSnapshot22:
        return self.tooling.snapshot()

    def create(self, asset_path: str, *, width: int, height: int) -> TerrainEditorSession:
        document = self.tooling.create(asset_path, width=width, height=height)
        self._status = f"Created terrain {self.tooling.snapshot().selected}"
        return document

    def select(self, asset_path: str) -> TerrainEditorSession:
        document = self.tooling.open(asset_path)
        self._status = f"Selected terrain {self.tooling.snapshot().selected}"
        return document

    def sculpt(
        self,
        *,
        x: float,
        z: float,
        radius: float,
        strength: float,
        mode: str = "raise",
    ) -> int:
        document = self.tooling.selected_document()
        target_height = None
        if mode == "flatten":
            runtime = document.runtime_preview()
            target_height = runtime.sample_height(x, z, clamp=True) / document.asset.config.height_scale
        stroke = document.sculpt(
            x=x,
            z=z,
            radius=radius,
            strength=strength,
            mode=mode,
            target_height=target_height,
        )
        self._status = f"{mode.title()} terrain stroke · {len(stroke.samples)} samples"
        return len(stroke.samples)

    def paint(
        self,
        layer: int,
        *,
        x: float,
        z: float,
        radius: float,
        strength: float,
    ) -> int:
        document = self.tooling.selected_document()
        changed = document.paint(layer, x=x, z=z, radius=radius, strength=strength)
        self._status = f"Painted layer {layer} · {changed} samples"
        return changed

    def add_foliage(self, asset: str, *, x: float, z: float) -> None:
        document = self.tooling.selected_document()
        document.add_foliage(FoliagePlacement(asset, x, z))
        self._status = f"Placed foliage {asset}"

    def undo(self) -> bool:
        changed = self.tooling.selected_document().undo()
        self._status = "Undid terrain stroke" if changed else "Nothing to undo"
        return changed

    def redo(self) -> bool:
        changed = self.tooling.selected_document().redo()
        self._status = "Redid terrain stroke" if changed else "Nothing to redo"
        return changed

    def save(self) -> tuple[Path, ...]:
        saved = self.tooling.save()
        self._status = f"Saved {len(saved)} terrain asset(s)"
        return saved

    def reload(self) -> TerrainEditorSession:
        document = self.tooling.reload_selected()
        self._status = "Reloaded terrain from project"
        return document

    def runtime_preview(self) -> TerrainRuntimePreview22:
        document = self.tooling.selected_document()
        runtime = document.runtime_preview()
        streaming = document.asset.runtime_streaming_settings()
        preview = TerrainRuntimePreview22(
            world_width=runtime.world_width,
            world_depth=runtime.world_depth,
            chunks_x=runtime.chunk_count_x,
            chunks_z=runtime.chunk_count_z,
            lod_count=len(runtime.config.lod_steps),
            active_radius_chunks=streaming.active_radius_chunks,
            preload_radius_chunks=streaming.preload_radius_chunks,
        )
        self._status = (
            f"Runtime preview · {preview.chunks_x * preview.chunks_z} chunks · "
            f"{preview.lod_count} LOD levels"
        )
        return preview
