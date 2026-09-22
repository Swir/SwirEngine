"""Verify SwirEngine 2.1 Build/Export Wizard against representative real games."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from verify_real_game_production_1_9 import (
    FIXTURES,
    FixtureSpec,
    _host_target,
    _prepare_project,
)

from swirengine.editor_build_export_frontend21 import EditorBuildExportPanelController21
from swirengine.editor_build_export_tooling21 import EditorBuildExportTooling21
from swirengine.exporting import ExportTarget, NativeBuildError, PackagingProfile, ProjectExporter

_EXPECTED_FIXTURES = {"2d-game", "3d-game", "multiplayer-game"}
_ICON_PATH = "assets/build-icon.png"
_ICON_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _fingerprint(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha256_bytes(encoded)


def _mismatched_desktop_target() -> ExportTarget:
    host = _host_target()
    if host is ExportTarget.WINDOWS:
        return ExportTarget.LINUX
    return ExportTarget.WINDOWS


def _profile_for_fixture(name: str, files: tuple[str, ...]) -> PackagingProfile:
    includes = ["assets", "config", "scenes"]
    includes.extend(value for value in files if value != "run_game.py")
    return PackagingProfile(
        name="shipping",
        target=_host_target(),
        entrypoint="run_game.py",
        app_name=f"SwirEngine-{name}",
        include=tuple(includes),
        icon=_ICON_PATH,
        onefile=False,
        console=True,
        metadata={
            "fixture": name,
            "gate": "swirengine-2.1-milestone-9",
        },
    )


def _validate_fixture(
    repository: Path,
    workspace: Path,
    fixture: FixtureSpec,
) -> dict[str, object]:
    name = fixture.name
    project_root = workspace / name
    _prepare_project(repository, project_root, fixture)
    icon_path = project_root / _ICON_PATH
    icon_path.parent.mkdir(parents=True, exist_ok=True)
    icon_path.write_bytes(_ICON_BYTES)

    tooling = EditorBuildExportTooling21(project_root, project_name=f"SwirEngine-{name}")
    profile = _profile_for_fixture(name, fixture.files)
    tooling.upsert_profile(profile)
    tooling.select_profile(profile.name)
    tooling.save()

    # The creator-authored profile must survive disk round-trip before any shipping claim.
    reloaded = EditorBuildExportTooling21(project_root, project_name=f"SwirEngine-{name}")
    controller = EditorBuildExportPanelController21(reloaded)
    frame = controller.preflight()
    active = reloaded.config.active
    if active != profile:
        raise RuntimeError(f"{name} build/export profile changed after save/reload")
    if frame.target != _host_target().value:
        raise RuntimeError(f"{name} preflight selected the wrong host target")
    if frame.experimental:
        raise RuntimeError(f"{name} desktop preflight was incorrectly marked experimental")
    if not frame.native_build_planned:
        raise RuntimeError(f"{name} desktop preflight did not expose a native build plan")

    artifact = controller.stage()
    if not artifact.checksums_verified:
        raise RuntimeError(f"{name} staged artifact failed checksum inspection")
    if artifact.native_spec is None:
        raise RuntimeError(f"{name} desktop staging did not create a native build spec")

    manifest_path = Path(artifact.manifest)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    files_payload = payload.get("files")
    checksums = payload.get("sha256")
    if not isinstance(files_payload, list) or not isinstance(checksums, dict):
        raise RuntimeError(f"{name} staged manifest is missing deterministic file evidence")
    if _ICON_PATH not in files_payload:
        raise RuntimeError(f"{name} authored icon was not shipped")
    if payload.get("metadata") != profile.metadata:
        raise RuntimeError(f"{name} authored metadata did not reach the shipping manifest")
    icon_digest = checksums.get(_ICON_PATH)
    if icon_digest != _sha256_bytes(_ICON_BYTES):
        raise RuntimeError(f"{name} staged icon checksum does not match authored source")

    portable_evidence = {
        "name": name,
        "target": frame.target,
        "planned_file_count": frame.planned_file_count,
        "staged_file_count": artifact.file_count,
        "files": files_payload,
        "sha256": checksums,
        "metadata": payload["metadata"],
        "icon": active.icon,
        "native_build_planned": frame.native_build_planned,
        "checksums_verified": artifact.checksums_verified,
    }
    return {
        "name": name,
        "target": frame.target,
        "planned_file_count": frame.planned_file_count,
        "staged_file_count": artifact.file_count,
        "checksums_verified": artifact.checksums_verified,
        "icon_configured": active.icon == _ICON_PATH,
        "metadata_verified": payload["metadata"] == profile.metadata,
        "profile_roundtrip": active == profile,
        "native_build_planned": frame.native_build_planned,
        "fingerprint": _fingerprint(portable_evidence),
    }


def _verify_cross_compile_rejection(repository: Path, workspace: Path) -> bool:
    fixture = FIXTURES[0]
    project_root = workspace / "cross-compile-rejection"
    _prepare_project(repository, project_root, fixture)
    profile = PackagingProfile(
        name="wrong-host",
        target=_mismatched_desktop_target(),
        entrypoint="run_game.py",
        include=("assets", "config", "scenes", "procedural_art.py"),
    )
    runner_called = False

    def runner(*_args: object, **_kwargs: object) -> object:
        nonlocal runner_called
        runner_called = True
        raise AssertionError("runner must not execute for cross-host native builds")

    try:
        ProjectExporter(project_root).build_native(
            profile,
            project_root / "dist" / "wrong-host",
            runner=runner,
        )
    except NativeBuildError:
        pass
    else:
        raise RuntimeError("cross-host native build was not rejected")
    if runner_called:
        raise RuntimeError("cross-host native build reached the external build runner")
    return True


def run_gate(repository: Path, workspace: Path) -> dict[str, object]:
    repository = repository.expanduser().resolve()
    workspace = workspace.expanduser().resolve()
    evidence = [_validate_fixture(repository, workspace, fixture) for fixture in FIXTURES]
    names = {str(item["name"]) for item in evidence}
    if names != _EXPECTED_FIXTURES:
        raise RuntimeError(f"unexpected representative fixture set: {sorted(names)!r}")
    cross_compile_rejected = _verify_cross_compile_rejection(repository, workspace)
    aggregate = {
        "fixtures": evidence,
        "cross_compile_rejected": cross_compile_rejected,
    }
    return {
        "status": "ok",
        "scope": "SwirEngine 2.1 Milestone 9 Build/Export Real-Game Gate",
        "fixture_count": len(evidence),
        "fixture_names": sorted(names),
        "host_target": _host_target().value,
        "cross_compile_rejected": cross_compile_rejected,
        "fixtures": evidence,
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
    with TemporaryDirectory(prefix="swirengine-editor-export-2-1-") as directory:
        report = run_gate(args.repository, Path(directory))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
