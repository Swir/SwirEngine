from __future__ import annotations

from pathlib import Path


class AssetManager:
    """Resolve and alias project assets without coupling them to the renderer."""

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

    def clear_aliases(self) -> None:
        self._aliases.clear()

    def _resolve_path(self, path: str | Path) -> Path:
        candidate = Path(path).expanduser()
        if candidate.is_absolute():
            return candidate
        return self.root / candidate
