from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .filewatch import PollingFileWatcher

AssetLoader = Callable[[Path], Any]
AssetInvalidator = Callable[[Path], None]


@dataclass(frozen=True, slots=True)
class AssetInfo:
    """One discovered asset entry relative to an ``AssetManager`` root."""

    path: Path
    relative_path: Path
    size_bytes: int
    suffix: str


@dataclass(frozen=True, slots=True)
class AssetDiagnostics:
    """Snapshot of project asset health for tooling and debug UIs."""

    root: Path
    files: tuple[AssetInfo, ...]
    missing_aliases: tuple[str, ...]
    total_bytes: int

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def healthy(self) -> bool:
        return not self.missing_aliases

    def by_suffix(self, suffix: str) -> tuple[AssetInfo, ...]:
        normalized = suffix.lower()
        if normalized and not normalized.startswith("."):
            normalized = "." + normalized
        return tuple(item for item in self.files if item.suffix == normalized)


@dataclass(frozen=True, slots=True)
class AssetReloadResult:
    """Result of one filesystem-driven asset invalidation/reload transaction."""

    path: Path
    kind: str
    aliases: tuple[str, ...]
    was_cached: bool
    reloaded: bool
    error: str | None = None


class AssetManager:
    """Resolve, cache, watch and inspect project assets without renderer coupling.

    Loaders are registered by file suffix. Loaded values are cached by canonical path so aliases
    and direct paths share one runtime object. File changes can invalidate that cache and notify
    renderer/audio/tooling invalidators before an optional reload.
    """

    def __init__(
        self,
        root: str | Path = "assets",
        *,
        watcher: PollingFileWatcher | None = None,
    ) -> None:
        self.root = Path(root)
        self._aliases: dict[str, Path] = {}
        self._loaders: dict[str, AssetLoader] = {}
        self._cache: dict[Path, Any] = {}
        self._invalidators: list[AssetInvalidator] = []
        self.watcher = watcher or PollingFileWatcher()

    def register(self, name: str, path: str | Path) -> Path:
        if not name:
            raise ValueError("asset alias cannot be empty")
        resolved = self._resolve_path(path)
        self._aliases[name] = resolved
        return resolved

    def unregister(self, name: str) -> bool:
        return self._aliases.pop(name, None) is not None

    def resolve(self, asset: str | Path, *, strict: bool = False) -> Path:
        key = str(asset)
        path = self._aliases.get(key)
        if path is None:
            path = self._resolve_path(asset)
        if strict and not path.exists():
            raise FileNotFoundError(path)
        return path

    def require(self, asset: str | Path) -> Path:
        return self.resolve(asset, strict=True)

    def exists(self, asset: str | Path) -> bool:
        return self.resolve(asset).exists()

    def aliases(self) -> dict[str, Path]:
        """Return a defensive copy of registered aliases."""
        return dict(self._aliases)

    def register_loader(self, suffix: str, loader: AssetLoader) -> None:
        normalized = self._normalize_suffix(suffix)
        if not normalized:
            raise ValueError("asset loader suffix cannot be empty")
        if not callable(loader):
            raise TypeError("asset loader must be callable")
        self._loaders[normalized] = loader

    def unregister_loader(self, suffix: str) -> bool:
        return self._loaders.pop(self._normalize_suffix(suffix), None) is not None

    def loader_suffixes(self) -> tuple[str, ...]:
        return tuple(sorted(self._loaders))

    def load(self, asset: str | Path, *, cache: bool = True) -> Any:
        path = self.require(asset).expanduser().resolve()
        if cache and path in self._cache:
            return self._cache[path]
        loader = self._loaders.get(path.suffix.lower())
        if loader is None:
            raise ValueError(f"no asset loader registered for suffix {path.suffix.lower()!r}")
        value = loader(path)
        if cache:
            self._cache[path] = value
        return value

    def cached(self, asset: str | Path) -> bool:
        return self.resolve(asset).expanduser().resolve() in self._cache

    def cached_paths(self) -> tuple[Path, ...]:
        return tuple(sorted(self._cache, key=lambda path: path.as_posix().lower()))

    def invalidate(self, asset: str | Path) -> bool:
        path = self.resolve(asset).expanduser().resolve()
        return self._invalidate_path(path)

    def clear_cache(self) -> int:
        paths = tuple(self._cache)
        for path in paths:
            self._invalidate_path(path)
        return len(paths)

    def add_invalidator(self, callback: AssetInvalidator) -> None:
        if not callable(callback):
            raise TypeError("asset invalidator must be callable")
        if callback not in self._invalidators:
            self._invalidators.append(callback)

    def remove_invalidator(self, callback: AssetInvalidator) -> bool:
        try:
            self._invalidators.remove(callback)
        except ValueError:
            return False
        return True

    def watch(self, asset: str | Path) -> Path:
        return self.watcher.watch(self.resolve(asset))

    def unwatch(self, asset: str | Path) -> bool:
        return self.watcher.unwatch(self.resolve(asset))

    def watch_cached(self) -> tuple[Path, ...]:
        for path in self.cached_paths():
            self.watcher.watch(path)
        return self.watcher.paths

    def poll_changes(self, *, reload_cached: bool = True) -> tuple[AssetReloadResult, ...]:
        results: list[AssetReloadResult] = []
        for event in self.watcher.poll():
            path = event.path
            was_cached = path in self._cache
            aliases = tuple(sorted(name for name, target in self._aliases.items() if target.resolve() == path))
            self._invalidate_path(path)
            reloaded = False
            error: str | None = None
            if reload_cached and was_cached and event.kind != "deleted":
                loader = self._loaders.get(path.suffix.lower())
                if loader is not None:
                    try:
                        self._cache[path] = loader(path)
                    except Exception as exc:  # noqa: BLE001 - user asset loaders may raise anything.
                        error = str(exc)
                    else:
                        reloaded = True
            results.append(
                AssetReloadResult(
                    path=path,
                    kind=event.kind,
                    aliases=aliases,
                    was_cached=was_cached,
                    reloaded=reloaded,
                    error=error,
                )
            )
        return tuple(results)

    def scan(self, *, recursive: bool = True) -> tuple[AssetInfo, ...]:
        """Return deterministic metadata for files currently present under the asset root."""
        root = self.root.expanduser().resolve()
        if not root.exists():
            return ()
        if not root.is_dir():
            raise NotADirectoryError(root)

        iterator = root.rglob("*") if recursive else root.glob("*")
        files: list[AssetInfo] = []
        for path in iterator:
            if not path.is_file():
                continue
            resolved = path.resolve()
            files.append(
                AssetInfo(
                    path=resolved,
                    relative_path=resolved.relative_to(root),
                    size_bytes=resolved.stat().st_size,
                    suffix=resolved.suffix.lower(),
                )
            )
        files.sort(key=lambda item: item.relative_path.as_posix().lower())
        return tuple(files)

    def diagnostics(self, *, recursive: bool = True) -> AssetDiagnostics:
        """Inspect files plus alias health without loading any resource into RAM or GPU memory."""
        files = self.scan(recursive=recursive)
        missing = tuple(sorted(name for name, path in self._aliases.items() if not path.exists()))
        return AssetDiagnostics(
            root=self.root.expanduser().resolve(),
            files=files,
            missing_aliases=missing,
            total_bytes=sum(item.size_bytes for item in files),
        )

    def clear_aliases(self) -> None:
        self._aliases.clear()

    def _invalidate_path(self, path: Path) -> bool:
        existed = self._cache.pop(path, None) is not None
        for callback in tuple(self._invalidators):
            callback(path)
        return existed

    @staticmethod
    def _normalize_suffix(suffix: str) -> str:
        normalized = str(suffix).strip().lower()
        if normalized and not normalized.startswith("."):
            normalized = "." + normalized
        return normalized

    def _resolve_path(self, path: str | Path) -> Path:
        candidate = Path(path).expanduser()
        if candidate.is_absolute():
            return candidate
        return self.root / candidate
