from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .plugins import PluginManager


@dataclass(frozen=True, slots=True)
class FileChangeEvent:
    """One stable filesystem change detected by :class:`PollingFileWatcher`."""

    path: Path
    kind: str


@dataclass(frozen=True, slots=True)
class ReloadResult:
    """Result of one automatic plugin reload attempt."""

    plugin: str
    path: Path
    reloaded: bool
    error: str | None = None


@dataclass(frozen=True, slots=True)
class _FileStamp:
    exists: bool
    mtime_ns: int
    size: int


class PollingFileWatcher:
    """Dependency-free file watcher designed for deterministic editor/dev polling.

    The watcher performs no background I/O and owns no threads. Call :meth:`poll`
    from the game/editor update loop at whatever cadence is appropriate. This makes
    shutdown deterministic and keeps the watcher portable across Windows, Linux and
    macOS without an optional native dependency.
    """

    def __init__(self) -> None:
        self._paths: dict[Path, _FileStamp] = {}

    @property
    def paths(self) -> tuple[Path, ...]:
        return tuple(self._paths)

    def watch(self, path: str | Path) -> Path:
        resolved = Path(path).expanduser().resolve()
        self._paths.setdefault(resolved, self._stamp(resolved))
        return resolved

    def unwatch(self, path: str | Path) -> bool:
        resolved = Path(path).expanduser().resolve()
        return self._paths.pop(resolved, None) is not None

    def clear(self) -> None:
        self._paths.clear()

    def poll(self) -> tuple[FileChangeEvent, ...]:
        events: list[FileChangeEvent] = []
        for path, previous in tuple(self._paths.items()):
            current = self._stamp(path)
            if current == previous:
                continue
            self._paths[path] = current
            if previous.exists and not current.exists:
                kind = "deleted"
            elif not previous.exists and current.exists:
                kind = "created"
            else:
                kind = "modified"
            events.append(FileChangeEvent(path=path, kind=kind))
        return tuple(events)

    @staticmethod
    def _stamp(path: Path) -> _FileStamp:
        try:
            stat = path.stat()
        except FileNotFoundError:
            return _FileStamp(False, 0, 0)
        return _FileStamp(True, stat.st_mtime_ns, stat.st_size)


class PluginAutoReloader:
    """Map source files to module-backed plugins and reload them after edits."""

    def __init__(
        self,
        manager: PluginManager,
        *,
        watcher: PollingFileWatcher | None = None,
        preserve_state: bool = True,
        on_result: Callable[[ReloadResult], None] | None = None,
    ) -> None:
        self.manager = manager
        self.watcher = watcher or PollingFileWatcher()
        self.preserve_state = bool(preserve_state)
        self.on_result = on_result
        self._plugins_by_path: dict[Path, str] = {}

    @property
    def watched_plugins(self) -> tuple[tuple[Path, str], ...]:
        return tuple(self._plugins_by_path.items())

    def watch(self, plugin: str, path: str | Path) -> Path:
        self.manager.info(plugin)
        resolved = self.watcher.watch(path)
        self._plugins_by_path[resolved] = plugin
        return resolved

    def unwatch(self, path: str | Path) -> bool:
        resolved = Path(path).expanduser().resolve()
        removed = self._plugins_by_path.pop(resolved, None) is not None
        self.watcher.unwatch(resolved)
        return removed

    def poll(self) -> tuple[ReloadResult, ...]:
        results: list[ReloadResult] = []
        for event in self.watcher.poll():
            plugin = self._plugins_by_path.get(event.path)
            if plugin is None or event.kind == "deleted":
                continue
            try:
                self.manager.reload(plugin, preserve_state=self.preserve_state)
            except Exception as exc:  # noqa: BLE001 - plugin code can raise arbitrary errors.
                result = ReloadResult(plugin, event.path, False, str(exc))
            else:
                result = ReloadResult(plugin, event.path, True)
            results.append(result)
            if self.on_result is not None:
                self.on_result(result)
        return tuple(results)
