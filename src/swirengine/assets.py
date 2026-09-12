from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


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


class AssetManager:
    """Resolve, alias and inspect project assets without coupling them to the renderer."""

    def __init__(self, root: str | Path = "assets") -> None:
        self.root = Path(root)
        self._aliases: dict[str, Path] = {}

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

    def _resolve_path(self, path: str | Path) -> Path:
        candidate = Path(path).expanduser()
        if candidate.is_absolute():
            return candidate
        return self.root / candidate
