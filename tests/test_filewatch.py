from __future__ import annotations

import os
from pathlib import Path

from swirengine.filewatch import PluginAutoReloader, PollingFileWatcher


class FakeManager:
    def __init__(self) -> None:
        self.reloads: list[tuple[str, bool]] = []
        self.known = {"demo"}

    def info(self, name: str) -> object:
        if name not in self.known:
            raise RuntimeError("unknown plugin")
        return object()

    def reload(self, name: str, *, preserve_state: bool = True) -> object:
        self.reloads.append((name, preserve_state))
        return object()


def _bump(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))


def test_watcher_detects_modify_delete_and_recreate(tmp_path: Path) -> None:
    path = tmp_path / "plugin.py"
    path.write_text("v1", encoding="utf-8")
    watcher = PollingFileWatcher()
    watcher.watch(path)

    assert watcher.poll() == ()
    _bump(path, "version-two")
    events = watcher.poll()
    assert len(events) == 1
    assert events[0].kind == "modified"
    assert events[0].path == path.resolve()

    path.unlink()
    assert watcher.poll()[0].kind == "deleted"

    path.write_text("v3", encoding="utf-8")
    assert watcher.poll()[0].kind == "created"


def test_auto_reloader_reloads_modified_plugin_and_preserves_state(tmp_path: Path) -> None:
    path = tmp_path / "demo.py"
    path.write_text("v1", encoding="utf-8")
    manager = FakeManager()
    results = []
    reloader = PluginAutoReloader(manager, on_result=results.append)  # type: ignore[arg-type]
    reloader.watch("demo", path)

    _bump(path, "v2 changed")
    outcome = reloader.poll()

    assert manager.reloads == [("demo", True)]
    assert len(outcome) == 1
    assert outcome[0].reloaded is True
    assert outcome[0].error is None
    assert results == list(outcome)


def test_auto_reloader_can_disable_state_preservation(tmp_path: Path) -> None:
    path = tmp_path / "demo.py"
    path.write_text("v1", encoding="utf-8")
    manager = FakeManager()
    reloader = PluginAutoReloader(manager, preserve_state=False)  # type: ignore[arg-type]
    reloader.watch("demo", path)

    _bump(path, "v2")
    reloader.poll()

    assert manager.reloads == [("demo", False)]


def test_deleted_file_does_not_attempt_reload(tmp_path: Path) -> None:
    path = tmp_path / "demo.py"
    path.write_text("v1", encoding="utf-8")
    manager = FakeManager()
    reloader = PluginAutoReloader(manager)  # type: ignore[arg-type]
    reloader.watch("demo", path)

    path.unlink()
    assert reloader.poll() == ()
    assert manager.reloads == []
