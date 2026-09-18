"""Verify representative SwirEngine games through the 2.0 source-to-shipping gate."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory

from verify_real_game_production_1_9 import (
    FIXTURES,
    _host_target,
    _prepare_project,
    _validate_project,
    run_production_gate,
)

from swirengine import __version__
from swirengine.diagnostics19 import (
    RuntimeCrashReport,
    RuntimeLogBuffer,
    capture_exception,
    identity_from_project,
)
from swirengine.exporting import PackagingProfile, ProjectExporter
from swirengine.project19 import ProjectManifest

_EXPECTED_FIXTURES = {"2d-game", "3d-game", "multiplayer-game"}
_FORBIDDEN_SHIPPING_PARTS = {
    "user-data",
    "profiles",
    "saves",
    "input-overrides.json",
}
_DIAGNOSTIC_SECRET = "fixture-secret-do-not-export"


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def validate_gate_report(report: dict[str, object], *, runtime_required: bool) -> None:
    if report.get("status") != "ok":
        raise RuntimeError("1.9 production foundation did not report success")
    fixtures = report.get("fixtures")
    if not isinstance(fixtures, list) or len(fixtures) != 3:
        raise RuntimeError("2.0 shipping gate requires exactly three representative fixtures")

    names: set[str] = set()
    for fixture in fixtures:
        if not isinstance(fixture, dict):
            raise TypeError("fixture report must be a mapping")
        name = fixture.get("name")
        if not isinstance(name, str):
            raise TypeError("fixture report is missing its name")
        names.add(name)

        exported = fixture.get("exported_files")
        if not isinstance(exported, Sequence) or isinstance(exported, (str, bytes)):
            raise TypeError(f"{name} exported_files must be a sequence")
        for value in exported:
            if not isinstance(value, str):
                raise TypeError(f"{name} exported file names must be strings")
            normalized = value.replace("\\", "/").lower().split("/")
            if any(part in _FORBIDDEN_SHIPPING_PARTS for part in normalized):
                raise RuntimeError(f"{name} leaked player-local data into shipping content: {value}")

        for key in (
            "scene_fingerprint",
            "content_fingerprint",
            "input_fingerprint",
            "settings_fingerprint",
            "game_state_fingerprint",
            "export_manifest_sha256",
            "fingerprint",
        ):
            if not _is_sha256(fixture.get(key)):
                raise RuntimeError(f"{name} has invalid deterministic evidence: {key}")

        if runtime_required:
            if fixture.get("source_runtime_ok") is not True:
                raise RuntimeError(f"{name} source runtime was not verified")
            if fixture.get("staged_runtime_ok") is not True:
                raise RuntimeError(f"{name} staged runtime was not verified")

    if names != _EXPECTED_FIXTURES:
        raise RuntimeError(f"unexpected representative fixture set: {sorted(names)!r}")
    if not _is_sha256(report.get("fingerprint")):
        raise RuntimeError("aggregate production fingerprint is invalid")


def verify_runtime_diagnostics(repository: Path, workspace: Path) -> dict[str, str]:
    """Exercise bounded privacy-safe diagnostics for every representative project."""

    evidence: dict[str, str] = {}
    for fixture in FIXTURES:
        project_root = workspace / fixture.name
        _prepare_project(repository, project_root, fixture)
        manifest = ProjectManifest.load(project_root / "swirproject.toml")
        identity = identity_from_project(
            manifest,
            engine_version=__version__,
            build_id="real-game-shipping-2.0",
            profile="shipping-gate",
        )
        logs = RuntimeLogBuffer(capacity=8)
        logs.record(
            "info",
            "representative game diagnostic probe",
            fixture=fixture.name,
            token=_DIAGNOSTIC_SECRET,
        )
        try:
            raise RuntimeError(
                f"diagnostic probe for {project_root} token={_DIAGNOSTIC_SECRET}"
            )
        except RuntimeError as exc:
            report = capture_exception(
                exc,
                identity=identity,
                logs=logs,
                diagnostics={
                    "fixture": fixture.name,
                    "project_root": str(project_root),
                    "token": _DIAGNOSTIC_SECRET,
                },
                performance={"frame_ms": 16.0, "draw_calls": 1},
                project_root=project_root,
            )

        encoded = report.to_json(indent=None)
        if _DIAGNOSTIC_SECRET in encoded:
            raise RuntimeError(f"{fixture.name} diagnostics leaked a secret value")
        if str(project_root) in encoded:
            raise RuntimeError(f"{fixture.name} diagnostics leaked the project root")
        decoded = json.loads(encoded)
        if not isinstance(decoded, dict):
            raise TypeError(f"{fixture.name} diagnostics did not produce an object report")
        roundtrip = RuntimeCrashReport.from_dict(decoded)
        if roundtrip.fingerprint != report.fingerprint:
            raise RuntimeError(f"{fixture.name} diagnostics fingerprint changed after roundtrip")
        if not _is_sha256(report.fingerprint):
            raise RuntimeError(f"{fixture.name} diagnostics fingerprint is invalid")
        evidence[fixture.name] = report.fingerprint

    if set(evidence) != _EXPECTED_FIXTURES:
        raise RuntimeError("runtime diagnostics did not cover every representative fixture")
    return dict(sorted(evidence.items()))


def verify_failure_paths(repository: Path, workspace: Path) -> dict[str, bool]:
    """Prove malformed shipping content fails before a successful package can be claimed."""

    missing_scene_root = workspace / "missing-scene"
    _prepare_project(repository, missing_scene_root, FIXTURES[0])
    (missing_scene_root / "scenes" / "gameplay.swirscene").unlink()
    missing_scene_rejected = False
    try:
        _validate_project(missing_scene_root)
    except (FileNotFoundError, OSError, RuntimeError, ValueError):
        missing_scene_rejected = True
    if not missing_scene_rejected:
        raise RuntimeError("missing declared gameplay scene was accepted by production validation")

    missing_entry_root = workspace / "missing-entrypoint"
    _prepare_project(repository, missing_entry_root, FIXTURES[0])
    (missing_entry_root / "run_game.py").unlink()
    profile = PackagingProfile(
        name="real-game-2.0-missing-entrypoint",
        target=_host_target(),
        entrypoint="run_game.py",
        include=("assets", "config", "procedural_art.py"),
        console=True,
    )
    missing_entrypoint_rejected = False
    try:
        ProjectExporter(missing_entry_root).export(profile, workspace / "invalid-staged")
    except (FileNotFoundError, OSError, RuntimeError, ValueError):
        missing_entrypoint_rejected = True
    if not missing_entrypoint_rejected:
        raise RuntimeError("shipping export accepted a missing project entrypoint")

    return {
        "missing_scene_rejected": True,
        "missing_entrypoint_rejected": True,
    }


def run_shipping_gate(
    repository: Path,
    workspace: Path,
    *,
    run_runtime: bool = True,
) -> dict[str, object]:
    repository = repository.resolve()
    production = run_production_gate(repository, workspace / "production", run_runtime=run_runtime)
    validate_gate_report(production, runtime_required=run_runtime)
    diagnostics = verify_runtime_diagnostics(repository, workspace / "diagnostics")
    failures = verify_failure_paths(repository, workspace / "failure-paths")
    return {
        "status": "ok",
        "scope": "SwirEngine 2.0 Representative Real-Game Shipping Gate",
        "runtime_validation": run_runtime,
        "fixture_count": 3,
        "fixture_names": sorted(_EXPECTED_FIXTURES),
        "production_fingerprint": production["fingerprint"],
        "diagnostic_fingerprints": diagnostics,
        "failure_paths": failures,
        "player_data_boundary": "external-to-shipping-content",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="SwirEngine repository root",
    )
    parser.add_argument(
        "--staging-only",
        action="store_true",
        help="validate staging and failure paths without launching source/staged entrypoints",
    )
    args = parser.parse_args()

    with TemporaryDirectory(prefix="swirengine-real-game-2-0-") as directory:
        report = run_shipping_gate(
            args.repository,
            Path(directory),
            run_runtime=not args.staging_only,
        )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
