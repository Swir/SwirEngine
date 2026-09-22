"""Verify SwirEngine 2.1 M10 through representative editor-authored real games."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from verify_real_game_production_1_9 import (
    FIXTURES,
    FixtureSpec,
    _host_target,
    _prepare_project,
    _require_runtime_ok,
    _run_entrypoint,
)

from swirengine.editor_build_export_frontend21 import EditorBuildExportPanelController21
from swirengine.editor_integrated_session21 import EditorIntegratedProjectSession21
from swirengine.exporting import PackagingProfile
from swirengine.serialization import SceneSerializer

_EXPECTED_FIXTURES = ["2d-game", "3d-game", "multiplayer-game"]
_AUTHORED_X = {
    "2d-game": 16,
    "3d-game": 32,
    "multiplayer-game": 48,
}


def _fingerprint(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _profile_for_fixture(spec: FixtureSpec) -> PackagingProfile:
    helpers = tuple(value for value in spec.files if value != "run_game.py")
    return PackagingProfile(
        name="editor-real-game",
        target=_host_target(),
        entrypoint="run_game.py",
        app_name=f"SwirEngine-{spec.name}",
        include=("assets", "config", "scenes", *helpers),
        console=True,
        metadata={
            "fixture": spec.name,
            "gate": "swirengine-2.1-milestone-10-editor",
        },
    )


def _open_editor(project_root: Path) -> EditorIntegratedProjectSession21:
    return EditorIntegratedProjectSession21.open(
        project_root,
        scene="scenes/title.swirscene",
        restore_state=False,
    )


def _validate_fixture(
    repository: Path,
    workspace: Path,
    spec: FixtureSpec,
) -> dict[str, object]:
    project_root = workspace / spec.name
    _prepare_project(repository, project_root, spec)

    session = _open_editor(project_root)
    if session.manifest.mode != spec.mode:
        raise RuntimeError(f"{spec.name} editor opened with unexpected mode {session.manifest.mode!r}")
    title = session.workspace.scene.find("production-gate-title")
    if title is None:
        raise RuntimeError(f"{spec.name} editor did not load the authored title scene")

    title_key = session.workspace.inspector.key_for(title)
    selected = session.controller.select(title_key)
    if selected is not title:
        raise RuntimeError(f"{spec.name} creator selection did not bind to the title object")

    authored_x = _AUTHORED_X[spec.name]
    session.controller.edit_property("x", str(authored_x))
    if float(title.x) != authored_x:
        raise RuntimeError(f"{spec.name} creator property edit did not reach the live scene")
    if not session.scenes.dirty:
        raise RuntimeError(f"{spec.name} creator property edit did not mark the scene dirty")

    preview = session.controller.preview
    if preview is None or not preview.step():
        raise RuntimeError(f"{spec.name} editor preview could not execute a runtime step")
    if preview.runtime.frame_count != 1:
        raise RuntimeError(f"{spec.name} editor preview did not advance exactly one frame")
    if float(title.x) != authored_x:
        raise RuntimeError(f"{spec.name} runtime preview leaked changes into editor state")

    build_controller = EditorBuildExportPanelController21(session.build_export)
    profile = _profile_for_fixture(spec)
    seed = PackagingProfile(
        name=profile.name,
        target=profile.target,
        entrypoint=profile.entrypoint,
        app_name=profile.app_name,
        include=profile.include,
        exclude=profile.exclude,
    )
    build_controller.upsert_profile(seed)
    configured = build_controller.configure_active_profile(
        name=profile.name,
        target=profile.target,
        entrypoint=profile.entrypoint,
        app_name=profile.effective_app_name,
        icon=None,
        onefile=profile.onefile,
        console=profile.console,
        metadata=profile.metadata,
    )
    if configured.target != _host_target().value:
        raise RuntimeError(f"{spec.name} editor build profile selected the wrong host target")
    session.save()

    reopened = _open_editor(project_root)
    persisted = reopened.workspace.scene.find("production-gate-title")
    if persisted is None or float(persisted.x) != authored_x:
        raise RuntimeError(f"{spec.name} editor-authored scene did not survive save/reopen")
    if reopened.build_export.config.active != profile:
        raise RuntimeError(f"{spec.name} editor build profile did not survive save/reopen")

    reopened_build = EditorBuildExportPanelController21(reopened.build_export)
    frame = reopened_build.preflight()
    if frame.planned_file_count <= 0:
        raise RuntimeError(f"{spec.name} editor export preflight produced an empty plan")
    artifact = reopened_build.stage()
    if not artifact.checksums_verified:
        raise RuntimeError(f"{spec.name} editor export failed staged checksum verification")

    staged_root = Path(artifact.output_dir)
    staged_scene = staged_root / "scenes" / "title.swirscene"
    if not staged_scene.is_file():
        raise RuntimeError(f"{spec.name} editor export omitted the authored title scene")
    staged_title = SceneSerializer().load_scene(staged_scene).find("production-gate-title")
    if staged_title is None or float(staged_title.x) != authored_x:
        raise RuntimeError(f"{spec.name} staged export lost the editor-authored scene change")

    source_runtime = _run_entrypoint(project_root, spec)
    _require_runtime_ok(source_runtime, label=f"{spec.name} editor-authored source runtime")
    staged_runtime = _run_entrypoint(staged_root, spec)
    _require_runtime_ok(staged_runtime, label=f"{spec.name} editor-exported staged runtime")

    evidence = {
        "name": spec.name,
        "mode": spec.mode,
        "authored_x": authored_x,
        "editor_save_reopen": True,
        "editor_preview_ok": True,
        "profile_roundtrip": reopened.build_export.config.active == profile,
        "planned_file_count": frame.planned_file_count,
        "staged_file_count": artifact.file_count,
        "checksums_verified": artifact.checksums_verified,
        "source_runtime_ok": source_runtime.returncode == 0,
        "staged_runtime_ok": staged_runtime.returncode == 0,
    }
    return {**evidence, "fingerprint": _fingerprint(evidence)}


def run_gate(repository: Path, workspace: Path) -> dict[str, object]:
    repository = repository.expanduser().resolve()
    workspace = workspace.expanduser().resolve()
    fixtures = [_validate_fixture(repository, workspace, spec) for spec in FIXTURES]
    names = [str(item["name"]) for item in fixtures]
    if names != _EXPECTED_FIXTURES:
        raise RuntimeError(f"unexpected representative fixture set: {names!r}")
    aggregate = {
        "host_target": _host_target().value,
        "fixtures": fixtures,
    }
    return {
        "status": "ok",
        "scope": "SwirEngine 2.1 Milestone 10 Real-Game Editor Gate",
        "fixture_count": len(fixtures),
        "fixture_names": names,
        "host_target": _host_target().value,
        "fixtures": fixtures,
        "fingerprint": _fingerprint(aggregate),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="SwirEngine repository root",
    )
    args = parser.parse_args()
    with TemporaryDirectory(prefix="swirengine-editor-real-game-2-1-") as directory:
        report = run_gate(args.repository, Path(directory))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
