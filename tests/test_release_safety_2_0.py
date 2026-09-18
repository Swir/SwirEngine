from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from swirengine.diagnostics19 import RuntimeIdentity, capture_exception, create_support_bundle
from swirengine.exporting import ExportTarget, PackagingProfile, ProjectExporter
from swirengine.release_safety20 import (
    ReleaseSafetyError,
    seal_export_staging,
    verify_export_staging,
    verify_support_bundle,
)


def _project(root: Path) -> Path:
    root.mkdir()
    (root / "main.py").write_text("print('release-safe')\n", encoding="utf-8")
    (root / "assets").mkdir()
    (root / "assets" / "sprite.txt").write_text("asset", encoding="utf-8")
    (root / "swirproject.toml").write_text('name = "Release Safe"\n', encoding="utf-8")
    return root


def _export(tmp_path: Path) -> Path:
    project = _project(tmp_path / "project")
    result = ProjectExporter(project).export(
        PackagingProfile(name="release-safe", target=ExportTarget.LINUX),
        tmp_path / "staged",
    )
    return result.output_dir


def _report(build_id: str, root: Path):
    identity = RuntimeIdentity(
        engine_version="2.0-candidate",
        project_name="Release Safe",
        project_fingerprint="project-fingerprint",
        build_id=build_id,
        profile="linux",
    )
    try:
        raise RuntimeError(f"failed safely under {root}; token=do-not-leak")
    except RuntimeError as exc:
        return capture_exception(
            exc,
            identity=identity,
            diagnostics={"scene": "arena", "api_key": "do-not-leak"},
            project_root=root,
        )


def test_export_integrity_seal_round_trip_and_build_identity(tmp_path: Path) -> None:
    staged = _export(tmp_path)

    initial = verify_export_staging(staged)
    assert initial.sealed is False
    assert len(initial.build_id) == 64
    sealed = seal_export_staging(staged)
    verified = verify_export_staging(
        staged,
        expected_build_id=initial.build_id,
        require_seal=True,
    )

    assert sealed.sealed is True
    assert verified.build_id == initial.build_id
    assert verified.files == ("assets/sprite.txt", "main.py", "swirproject.toml")
    assert verified.generated_sha256.keys() == {"swirengine-build.spec"}


def test_export_integrity_rejects_missing_tampered_and_unexpected_content(tmp_path: Path) -> None:
    staged = _export(tmp_path)
    identity = verify_export_staging(staged).build_id

    (staged / "assets" / "sprite.txt").write_text("tampered", encoding="utf-8")
    with pytest.raises(ReleaseSafetyError, match="checksum mismatch"):
        verify_export_staging(staged, expected_build_id=identity)

    (staged / "assets" / "sprite.txt").write_text("asset", encoding="utf-8")
    (staged / "unexpected.txt").write_text("not declared", encoding="utf-8")
    with pytest.raises(ReleaseSafetyError, match="unexpected files"):
        verify_export_staging(staged)

    (staged / "unexpected.txt").unlink()
    (staged / "main.py").unlink()
    with pytest.raises(ReleaseSafetyError, match="missing or unsafe"):
        verify_export_staging(staged)


def test_export_integrity_build_identity_covers_generated_native_spec(tmp_path: Path) -> None:
    staged = _export(tmp_path)
    sealed = seal_export_staging(staged)

    spec = staged / "swirengine-build.spec"
    spec.write_text(spec.read_text(encoding="utf-8") + "# tampered\n", encoding="utf-8")

    with pytest.raises(ReleaseSafetyError, match="build identity mismatch|seal build_id"):
        verify_export_staging(
            staged,
            expected_build_id=sealed.build_id,
            require_seal=True,
        )


def test_export_integrity_rejects_manifest_path_ambiguity(tmp_path: Path) -> None:
    staged = _export(tmp_path)
    manifest_path = staged / "swir-export.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"] = ["main.py", "MAIN.PY"]
    manifest["sha256"] = {
        "main.py": manifest["sha256"]["main.py"],
        "MAIN.PY": manifest["sha256"]["main.py"],
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ReleaseSafetyError, match="case collision"):
        verify_export_staging(staged)


def test_support_bundle_audit_links_report_to_verified_build(tmp_path: Path) -> None:
    staged = _export(tmp_path)
    sealed = seal_export_staging(staged)
    report = _report(sealed.build_id, tmp_path / "project")
    result = create_support_bundle(report, tmp_path / "support.zip")

    audit = verify_support_bundle(result.path, expected_build_id=sealed.build_id)

    assert audit.build_id == sealed.build_id
    assert audit.report_fingerprint == report.fingerprint
    assert audit.entries == ("bundle.json", "report.json")
    with zipfile.ZipFile(result.path) as archive:
        report_text = archive.read("report.json").decode("utf-8")
    assert "do-not-leak" not in report_text
    assert str(tmp_path) not in report_text


def test_support_bundle_audit_rejects_injected_files_and_wrong_build(tmp_path: Path) -> None:
    staged = _export(tmp_path)
    sealed = seal_export_staging(staged)
    report = _report(sealed.build_id, tmp_path / "project")
    bundle = create_support_bundle(report, tmp_path / "support.zip").path

    with pytest.raises(ReleaseSafetyError, match="build identity mismatch"):
        verify_support_bundle(bundle, expected_build_id="0" * 64)

    injected = tmp_path / "injected.zip"
    with zipfile.ZipFile(bundle) as source, zipfile.ZipFile(injected, "w") as destination:
        for info in source.infolist():
            destination.writestr(info, source.read(info.filename))
        destination.writestr("private.txt", b"must never be accepted")

    with pytest.raises(ReleaseSafetyError, match="entries must be exactly"):
        verify_support_bundle(injected, expected_build_id=sealed.build_id)


def test_support_bundle_audit_rejects_hash_and_privacy_tampering(tmp_path: Path) -> None:
    staged = _export(tmp_path)
    sealed = seal_export_staging(staged)
    report = _report(sealed.build_id, tmp_path / "project")
    bundle = create_support_bundle(report, tmp_path / "support.zip").path

    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(bundle) as source:
        bundle_manifest = json.loads(source.read("bundle.json"))
        packaged_report = source.read("report.json")
    bundle_manifest["privacy"]["automatic_environment_capture"] = True
    with zipfile.ZipFile(tampered, "w") as destination:
        destination.writestr("bundle.json", json.dumps(bundle_manifest))
        destination.writestr("report.json", packaged_report)

    with pytest.raises(ReleaseSafetyError, match="privacy boundary"):
        verify_support_bundle(tampered, expected_build_id=sealed.build_id)

    bad_hash = tmp_path / "bad-hash.zip"
    bundle_manifest["privacy"]["automatic_environment_capture"] = False
    bundle_manifest["report_sha256"] = "0" * 64
    with zipfile.ZipFile(bad_hash, "w") as destination:
        destination.writestr("bundle.json", json.dumps(bundle_manifest))
        destination.writestr("report.json", packaged_report)

    with pytest.raises(ReleaseSafetyError, match="SHA-256"):
        verify_support_bundle(bad_hash, expected_build_id=sealed.build_id)
