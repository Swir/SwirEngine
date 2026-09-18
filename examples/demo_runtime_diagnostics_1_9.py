"""SwirEngine 1.9 privacy-safe crash report and support-bundle creator demo."""

from __future__ import annotations

import json
import runpy
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from swirengine.diagnostics19 import (
    RuntimeCrashReport,
    RuntimeLogBuffer,
    capture_exception,
    create_support_bundle,
    identity_from_project,
)
from swirengine.project19 import ProjectManifest


def _create_project(root: Path) -> ProjectManifest:
    (root / "scripts").mkdir()
    (root / "main.py").write_text("print('demo')\n", encoding="utf-8")
    (root / "swirproject.toml").write_text(
        """name = "Diagnostics Demo"
mode = "2d"
entrypoint = "main.py"

[content]
include = ["scripts"]
""",
        encoding="utf-8",
    )
    return ProjectManifest.load(root)


def _fault(root: Path) -> None:
    source = root / "scripts" / "gameplay.py"
    source.write_text("raise RuntimeError('simulated gameplay failure')\n", encoding="utf-8")
    runpy.run_path(str(source))


def main() -> int:
    with TemporaryDirectory(prefix="swir-diagnostics-demo-") as directory:
        root = Path(directory)
        manifest = _create_project(root)
        identity = identity_from_project(
            manifest,
            engine_version="1.9-source",
            build_id="creator-demo",
            profile="windows",
        )
        logs = RuntimeLogBuffer(capacity=16)
        logs.record("info", "boot complete", scene="menu")
        logs.record("info", "loading gameplay", scene="arena", token="not-exported")

        try:
            _fault(root)
        except RuntimeError as exc:
            report = capture_exception(
                exc,
                identity=identity,
                logs=logs,
                diagnostics={
                    "scene": "arena",
                    "players": 1,
                    "password": "redacted-by-contract",
                },
                project_root=root,
            )
        else:  # pragma: no cover - demo guard
            raise RuntimeError("diagnostics demo did not trigger its expected failure")

        report_path = report.export_json(root / "artifacts" / "crash-report.json")
        loaded = RuntimeCrashReport.load_json(report_path)
        if loaded.fingerprint != report.fingerprint:
            raise RuntimeError("runtime report round-trip changed its fingerprint")

        bundle = create_support_bundle(loaded, root / "artifacts" / "support.zip")
        with zipfile.ZipFile(bundle.path) as archive:
            bundle_manifest = json.loads(archive.read("bundle.json"))
            if tuple(sorted(archive.namelist())) != ("bundle.json", "report.json"):
                raise RuntimeError("support bundle contained an unexpected file")

        print("report fingerprint:", report.fingerprint)
        print("trace:", [frame.filename for frame in report.trace])
        print("bundle entries:", bundle.entries)
        print("user-file capture:", bundle_manifest["privacy"]["automatic_user_file_capture"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
