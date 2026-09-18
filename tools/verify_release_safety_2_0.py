from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path

from swirengine.diagnostics19 import RuntimeIdentity, capture_exception, create_support_bundle
from swirengine.exporting import ExportTarget, PackagingProfile, ProjectExporter
from swirengine.release_safety20 import (
    ReleaseSafetyError,
    seal_export_staging,
    verify_export_staging,
    verify_support_bundle,
)


def _create_project(root: Path) -> Path:
    project = root / "project"
    project.mkdir()
    (project / "main.py").write_text("print('m9-ok')\n", encoding="utf-8")
    (project / "assets").mkdir()
    (project / "assets" / "required.txt").write_text("required-content", encoding="utf-8")
    (project / "swirproject.toml").write_text('name = "M9 Fixture"\n', encoding="utf-8")
    return project


def _support_report(build_id: str, project: Path):
    identity = RuntimeIdentity(
        engine_version="2.0-candidate",
        project_name="M9 Fixture",
        project_fingerprint="m9-fixture",
        build_id=build_id,
        profile="linux",
    )
    try:
        raise RuntimeError(f"fixture failed at {project}; token=private-value")
    except RuntimeError as exc:
        return capture_exception(
            exc,
            identity=identity,
            diagnostics={"scene": "fixture", "password": "private-value"},
            project_root=project,
        )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="swir-release-safety-") as temp:
        root = Path(temp)
        project = _create_project(root)
        staged = ProjectExporter(project).export(
            PackagingProfile(name="m9-fixture", target=ExportTarget.LINUX),
            root / "staged",
        ).output_dir

        sealed = seal_export_staging(staged)
        verified = verify_export_staging(
            staged,
            expected_build_id=sealed.build_id,
            require_seal=True,
        )
        if len(verified.files) != 3:
            raise RuntimeError(f"unexpected verified file count: {len(verified.files)}")

        report = _support_report(verified.build_id, project)
        bundle = create_support_bundle(report, root / "support.zip").path
        audit = verify_support_bundle(bundle, expected_build_id=verified.build_id)
        if audit.entries != ("bundle.json", "report.json"):
            raise RuntimeError(f"unexpected support entries: {audit.entries}")

        required = staged / "assets" / "required.txt"
        original = required.read_bytes()
        required.write_bytes(b"tampered")
        try:
            verify_export_staging(staged, expected_build_id=verified.build_id, require_seal=True)
        except ReleaseSafetyError:
            pass
        else:
            raise RuntimeError("tampered staged content was accepted")
        required.write_bytes(original)
        verify_export_staging(staged, expected_build_id=verified.build_id, require_seal=True)

        injected = root / "support-injected.zip"
        with zipfile.ZipFile(bundle) as source, zipfile.ZipFile(injected, "w") as destination:
            for info in source.infolist():
                destination.writestr(info, source.read(info.filename))
            destination.writestr("private.txt", b"not allowed")
        try:
            verify_support_bundle(injected, expected_build_id=verified.build_id)
        except ReleaseSafetyError:
            pass
        else:
            raise RuntimeError("support bundle with an injected user file was accepted")

        with zipfile.ZipFile(bundle) as archive:
            bundle_manifest = json.loads(archive.read("bundle.json"))
        if bundle_manifest["privacy"] != {
            "automatic_argv_capture": False,
            "automatic_environment_capture": False,
            "automatic_user_file_capture": False,
            "trace_source_lines": False,
        }:
            raise RuntimeError("support bundle privacy declaration changed unexpectedly")

        print(
            "SwirEngine 2.0 release safety OK: "
            f"build_id={verified.build_id}, files={len(verified.files)}, "
            f"support_entries={len(audit.entries)}, privacy=locked"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
