from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable

from .assets import AssetInfo, AssetManager

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tga", ".hdr"}
_AUDIO_SUFFIXES = {".wav", ".mp3", ".ogg", ".flac", ".m4a"}
_MODEL_SUFFIXES = {".obj", ".gltf", ".glb", ".fbx", ".dae"}
_FONT_SUFFIXES = {".ttf", ".otf", ".woff", ".woff2"}
_DATA_SUFFIXES = {".json", ".toml", ".yaml", ".yml", ".csv"}
_SHADER_SUFFIXES = {".glsl", ".vert", ".frag", ".geom", ".comp"}
_SCRIPT_SUFFIXES = {".py"}


def classify_editor_asset(path: str | Path) -> str:
    """Return a stable creator-facing asset category from a filename suffix."""

    suffix = Path(path).suffix.lower()
    if suffix in _IMAGE_SUFFIXES:
        return "image"
    if suffix in _AUDIO_SUFFIXES:
        return "audio"
    if suffix in _MODEL_SUFFIXES:
        return "model"
    if suffix in _FONT_SUFFIXES:
        return "font"
    if suffix in _DATA_SUFFIXES:
        return "data"
    if suffix in _SHADER_SUFFIXES:
        return "shader"
    if suffix in _SCRIPT_SUFFIXES:
        return "script"
    return "other"


@dataclass(frozen=True, slots=True)
class EditorAssetEntry:
    """Immutable asset row ready for a visual editor front-end."""

    relative_path: str
    name: str
    folder: str
    kind: str
    suffix: str
    size_bytes: int
    aliases: tuple[str, ...] = ()
    cached: bool = False
    loadable: bool = False

    @property
    def key(self) -> str:
        return self.relative_path


@dataclass(frozen=True, slots=True)
class EditorAssetBrowserFrame:
    """Immutable result of one asset-browser query."""

    root: str
    entries: tuple[EditorAssetEntry, ...]
    folders: tuple[str, ...]
    kinds: tuple[str, ...]
    query: str = ""
    folder: str = ""
    kind: str | None = None
    selected_key: str | None = None
    total_files: int = 0
    total_bytes: int = 0
    missing_aliases: tuple[str, ...] = ()

    @property
    def visible_files(self) -> int:
        return len(self.entries)

    @property
    def healthy(self) -> bool:
        return not self.missing_aliases


class EditorAssetBrowser:
    """GUI-agnostic project asset browser backed by :class:`AssetManager`.

    The browser never loads file contents just to build its view. It reuses AssetManager scan,
    alias, cache and loader metadata so editor front-ends can search and inspect large projects
    without allocating textures, models or audio resources.
    """

    def __init__(self, manager: AssetManager) -> None:
        if not isinstance(manager, AssetManager):
            raise TypeError("manager must be an AssetManager")
        self.manager = manager
        self._query = ""
        self._folder = ""
        self._kind: str | None = None
        self._selected_key: str | None = None
        self._entries: tuple[EditorAssetEntry, ...] = ()
        self._folders: tuple[str, ...] = ()
        self._kinds: tuple[str, ...] = ()
        self._total_files = 0
        self._total_bytes = 0
        self._missing_aliases: tuple[str, ...] = ()
        self.refresh()

    @property
    def selected_key(self) -> str | None:
        return self._selected_key

    @property
    def selected_entry(self) -> EditorAssetEntry | None:
        if self._selected_key is None:
            return None
        return next((entry for entry in self._entries if entry.key == self._selected_key), None)

    def refresh(self) -> EditorAssetBrowserFrame:
        diagnostics = self.manager.diagnostics()
        aliases_by_path: dict[Path, list[str]] = {}
        for alias, path in self.manager.aliases().items():
            resolved = path.expanduser().resolve()
            aliases_by_path.setdefault(resolved, []).append(alias)

        loader_suffixes = set(self.manager.loader_suffixes())
        cached_paths = set(self.manager.cached_paths())
        entries = tuple(
            self._entry(info, aliases_by_path, loader_suffixes, cached_paths)
            for info in diagnostics.files
        )
        self._entries = entries
        self._folders = self._discover_folders(entries)
        self._kinds = tuple(sorted({entry.kind for entry in entries}))
        self._total_files = diagnostics.file_count
        self._total_bytes = diagnostics.total_bytes
        self._missing_aliases = diagnostics.missing_aliases
        if self._selected_key is not None and not any(
            entry.key == self._selected_key for entry in entries
        ):
            self._selected_key = None
        return self.frame()

    def set_filter(
        self,
        query: str = "",
        *,
        folder: str | Path = "",
        kind: str | None = None,
    ) -> EditorAssetBrowserFrame:
        self._query = str(query).strip()
        self._folder = self._normalize_folder(folder)
        normalized_kind = None if kind is None else str(kind).strip().lower()
        if normalized_kind == "":
            normalized_kind = None
        self._kind = normalized_kind
        return self.frame()

    def clear_filter(self) -> EditorAssetBrowserFrame:
        return self.set_filter()

    def select(self, asset: str | Path | None) -> EditorAssetEntry | None:
        if asset is None:
            self._selected_key = None
            return None
        key = self._normalize_relative(asset)
        entry = next((item for item in self._entries if item.key == key), None)
        if entry is None:
            raise KeyError(f"unknown editor asset {key!r}")
        self._selected_key = key
        return entry

    def resolve_selected(self) -> Path | None:
        entry = self.selected_entry
        if entry is None:
            return None
        return self.manager.resolve(entry.relative_path)

    def frame(self) -> EditorAssetBrowserFrame:
        query = self._query.casefold()
        folder = self._folder
        kind = self._kind
        entries = []
        for entry in self._entries:
            if query and query not in entry.relative_path.casefold() and query not in " ".join(
                entry.aliases
            ).casefold():
                continue
            if folder and entry.folder != folder and not entry.folder.startswith(folder + "/"):
                continue
            if kind is not None and entry.kind != kind:
                continue
            entries.append(entry)
        return EditorAssetBrowserFrame(
            root=str(self.manager.root),
            entries=tuple(entries),
            folders=self._folders,
            kinds=self._kinds,
            query=self._query,
            folder=folder,
            kind=kind,
            selected_key=self._selected_key,
            total_files=self._total_files,
            total_bytes=self._total_bytes,
            missing_aliases=self._missing_aliases,
        )

    @staticmethod
    def _entry(
        info: AssetInfo,
        aliases_by_path: dict[Path, list[str]],
        loader_suffixes: set[str],
        cached_paths: set[Path],
    ) -> EditorAssetEntry:
        relative = info.relative_path.as_posix()
        folder = info.relative_path.parent.as_posix()
        if folder == ".":
            folder = ""
        return EditorAssetEntry(
            relative_path=relative,
            name=info.relative_path.name,
            folder=folder,
            kind=classify_editor_asset(info.relative_path),
            suffix=info.suffix,
            size_bytes=info.size_bytes,
            aliases=tuple(sorted(aliases_by_path.get(info.path, ()))),
            cached=info.path in cached_paths,
            loadable=info.suffix in loader_suffixes,
        )

    @staticmethod
    def _discover_folders(entries: Iterable[EditorAssetEntry]) -> tuple[str, ...]:
        folders: set[str] = set()
        for entry in entries:
            path = PurePosixPath(entry.folder)
            while str(path) not in {"", "."}:
                folders.add(path.as_posix())
                path = path.parent
        return tuple(sorted(folders, key=lambda value: (value.count("/"), value.casefold())))

    @staticmethod
    def _normalize_relative(asset: str | Path) -> str:
        value = str(asset).replace("\\", "/").strip("/")
        if not value or value == ".":
            raise ValueError("asset path cannot be empty")
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("asset path must stay inside the asset root")
        return path.as_posix()

    @classmethod
    def _normalize_folder(cls, folder: str | Path) -> str:
        value = str(folder).replace("\\", "/").strip("/")
        if not value or value == ".":
            return ""
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("asset folder must stay inside the asset root")
        return path.as_posix()
