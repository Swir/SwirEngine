"""Verify the SwirEngine 2.0 integrated creator workflow on maintained game fixtures."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import verify_real_game_production_1_9 as real_game

from swirengine.creator_workflow20 import CreatorProjectWorkflow

REPOSITORY = Path(__file__).resolve().parents[1]


def _fingerprint(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def run_gate(repository: Path = REPOSITORY) -> dict[str, object]:
    reports: list[dict[str, object]] = []
    with TemporaryDirectory(prefix="swirengine-creator20-") as temp:
        workspace = Path(temp)
        for spec in real_game.FIXTURES:
            if spec.name not in {"2d-game", "3d-game"}:
                continue
            project = workspace / spec.name
            real_game._prepare_project(repository, project, spec)
            workflow = CreatorProjectWorkflow(project)
            workflow.prepare()
            report = workflow.inspect(
                platform="linux",
                environ={"XDG_DATA_HOME": str(workspace / "xdg")},
                home=workspace / "home",
            )
            if not report.ready:
                raise RuntimeError(
                    f"{spec.name} creator workflow is blocked: "
                    f"{[item.to_dict() for item in report.diagnostics]!r}"
                )
            if report.scene_packages != 2:
                raise RuntimeError(f"{spec.name} did not expose the expected scene registry")
            if report.content_nodes != 3:
                raise RuntimeError(f"{spec.name} did not expose the expected content build graph")
            if not report.input_defaults_present or not report.settings_defaults_present:
                raise RuntimeError(f"{spec.name} did not materialize editable shipping defaults")
            reports.append(
                {
                    "name": spec.name,
                    "mode": report.mode,
                    "scene_packages": report.scene_packages,
                    "content_nodes": report.content_nodes,
                    "manifest_fingerprint": report.manifest_fingerprint,
                    "run_plan_fingerprint": report.run_plan_fingerprint,
                    "scene_fingerprint": report.scene_fingerprint,
                    "content_fingerprint": report.content_fingerprint,
                    "shipping_defaults_fingerprint": report.shipping_defaults_fingerprint,
                    "workflow_fingerprint": report.fingerprint,
                }
            )

    payload = {
        "status": "ok",
        "scope": "SwirEngine 2.0 Creator Workflow & Integrated Tooling",
        "fixture_count": len(reports),
        "fixtures": reports,
    }
    payload["fingerprint"] = _fingerprint(reports)
    return payload


def main() -> int:
    print(json.dumps(run_gate(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
