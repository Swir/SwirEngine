from __future__ import annotations

from pathlib import Path

import pytest

from swirengine.game_state19 import (
    GameStateProductionError,
    ProductionGameStateSession,
    SaveProductionPolicy,
    project_app_id,
    resolve_user_data_root,
)
from swirengine.shipping19 import GameSettings
from swirengine.storage import MigrationRegistry


def test_project_app_id_and_platform_user_data_policy(tmp_path: Path) -> None:
    assert project_app_id("Neon Frontier!") == "Neon-Frontier"

    win = resolve_user_data_root(
        "Neon-Frontier",
        platform="win32",
        environ={"LOCALAPPDATA": str(tmp_path / "local")},
        home=tmp_path / "home",
    )
    assert win.platform == "windows"
    assert win.source == "LOCALAPPDATA"
    assert win.root == tmp_path / "local" / "SwirEngine" / "Neon-Frontier"

    linux = resolve_user_data_root(
        "Neon-Frontier",
        platform="linux",
        environ={"XDG_DATA_HOME": "relative-is-ignored"},
        home=tmp_path / "home",
    )
    assert linux.source == "xdg-fallback"
    assert linux.root == tmp_path / "home" / ".local" / "share" / "swirengine" / "Neon-Frontier"

    mac = resolve_user_data_root(
        "Neon-Frontier",
        platform="darwin",
        environ={},
        home=tmp_path / "home",
    )
    assert mac.root == (
        tmp_path
        / "home"
        / "Library"
        / "Application Support"
        / "SwirEngine"
        / "Neon-Frontier"
    )

    with pytest.raises(GameStateProductionError):
        resolve_user_data_root("game", platform="unsupported", environ={}, home=tmp_path)


def test_manual_save_background_roundtrip_and_slot_budget(tmp_path: Path) -> None:
    policy = SaveProductionPolicy(max_manual_slots=1, max_workers=1)
    with ProductionGameStateSession(
        "roundtrip",
        user_data_root=tmp_path,
        policy=policy,
    ) as session:
        request_id = session.submit_manual(
            "slot-1",
            {"level": 4, "health": 75},
            metadata={"scene": "factory"},
        )
        outcomes = session.run_until_idle(timeout=5.0)
        assert len(outcomes) == 1
        assert outcomes[0].request_id == request_id
        assert outcomes[0].successful
        assert session.diagnostics.pipeline.succeeded == 0
        assert session.diagnostics.pipeline.submitted_total == 1

        loaded = session.load("slot-1")
        assert loaded.data["level"] == 4
        assert loaded.data["health"] == 75
        assert loaded.metadata["save_kind"] == "manual"
        assert loaded.metadata["scene"] == "factory"

        with pytest.raises(GameStateProductionError, match="budget"):
            session.submit_manual("slot-2", {"level": 5})


def test_autosave_interval_rotation_and_latest_load(tmp_path: Path) -> None:
    policy = SaveProductionPolicy(
        autosave_keep=2,
        autosave_interval_seconds=10.0,
        max_workers=1,
    )
    with ProductionGameStateSession(
        "autosave-game",
        user_data_root=tmp_path,
        policy=policy,
    ) as session:
        first = session.submit_autosave({"tick": 1}, now=100.0)
        assert first is not None
        session.run_until_idle(timeout=5.0)

        assert session.submit_autosave({"tick": 2}, now=105.0) is None

        second = session.submit_autosave({"tick": 2}, now=111.0)
        assert second is not None
        session.run_until_idle(timeout=5.0)

        third = session.submit_autosave({"tick": 3}, now=122.0)
        assert third is not None
        session.run_until_idle(timeout=5.0)

        autosaves = session.list_autosaves()
        assert len(autosaves) == 2
        generations = [
            int(info.metadata["autosave_generation"])
            for info in autosaves
            if info.metadata
        ]
        assert generations == [3, 2]

        latest = session.load_latest_autosave()
        assert latest.data["tick"] == 3


def test_snapshot_budget_preflights_before_background_io(tmp_path: Path) -> None:
    policy = SaveProductionPolicy(max_snapshot_bytes=1024, max_workers=1)
    with ProductionGameStateSession(
        "bounded-game",
        user_data_root=tmp_path,
        policy=policy,
    ) as session:
        with pytest.raises(GameStateProductionError, match="max_snapshot_bytes"):
            session.submit_manual("huge", {"blob": "x" * 4096})
        assert session.diagnostics.snapshot_rejections == 1
        assert session.diagnostics.pipeline.submitted_total == 0


def test_recovery_and_migration_diagnostics(tmp_path: Path) -> None:
    with ProductionGameStateSession(
        "recovery-game",
        user_data_root=tmp_path,
        version=1,
    ) as session:
        session.submit_manual("campaign", {"score": 10})
        session.run_until_idle(timeout=5.0)
        session.submit_manual("campaign", {"score": 20})
        session.run_until_idle(timeout=5.0)
        store = session.manager.slot("campaign")
        store.path.write_text("{broken", encoding="utf-8")

        recovered = session.load("campaign", repair=True)
        assert recovered.recovered
        assert recovered.data["score"] == 10
        assert session.diagnostics.recoveries == 1

    migrations = MigrationRegistry()
    migrations.register(1, lambda values: {**values, "schema2": True})
    with ProductionGameStateSession(
        "recovery-game",
        user_data_root=tmp_path,
        version=2,
        migrations=migrations,
    ) as session:
        migrated = session.load("campaign", upgrade=True)
        assert migrated.migrations_applied == 1
        assert migrated.data["schema2"] is True
        assert session.diagnostics.migrations == 1


def test_shipping_settings_share_profile_user_data_root(tmp_path: Path) -> None:
    with ProductionGameStateSession(
        "settings-game",
        user_data_root=tmp_path,
    ) as session:
        store = session.settings_store()
        changed = GameSettings().with_accessibility(
            reduced_motion=True,
            subtitles=False,
        )
        store.save(changed)

        assert store.path == session.profile_directory / "config" / "game-settings.json"
        loaded = session.settings_store().load()
        assert loaded.accessibility.reduced_motion is True
        assert loaded.accessibility.subtitles is False


def test_reserved_autosave_namespace_and_closed_session(tmp_path: Path) -> None:
    session = ProductionGameStateSession("safe-game", user_data_root=tmp_path)
    with pytest.raises(GameStateProductionError, match="reserved prefix"):
        session.submit_manual("swir-autosave-1", {"x": 1})
    session.shutdown()
    with pytest.raises(RuntimeError, match="closed"):
        session.submit_manual("slot", {"x": 1})
