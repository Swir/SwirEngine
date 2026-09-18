"""Verify SwirEngine 1.9 source games through a production-style staging workflow."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from swirengine import Rectangle2D, Scene, SceneSerializer
from swirengine.content_build19 import ContentBuildGraph
from swirengine.exporting import ExportTarget, PackagingProfile, ProjectExporter
from swirengine.game_state19 import ProductionGameStateSession, SaveProductionPolicy
from swirengine.input import InputBinding
from swirengine.project19 import ProjectManifest
from swirengine.scene_packages19 import ScenePackageLoader, ScenePackageRegistry
from swirengine.shipping19 import (
    InputOverrideStore,
    ProjectShippingDefaults,
    REQUIRED_UI_ACTIONS,
)


@dataclass(frozen=True, slots=True)
class FixtureSpec:
    name: str
    source_dir: str
    mode: str
    files: tuple[str, ...]
    headless: bool = False


@dataclass(frozen=True, slots=True)
class FixtureReport:
    name: str
    mode: str
    source_files: tuple[str, ...]
    exported_files: tuple[str, ...]
    scene_fingerprint: str
    content_fingerprint: str
    input_fingerprint: str
    settings_fingerprint: str
    game_state_fingerprint: str
    export_manifest_sha256: str
    source_runtime_ok: bool | None
    staged_runtime_ok: bool | None
    fingerprint: str


FIXTURES = (
    FixtureSpec(
        name="2d-game",
        source_dir="examples/2d_game_demo",
        mode="2d",
        files=("run_game.py", "procedural_art.py"),
        headless=True,
    ),
    FixtureSpec(
        name="3d-game",
        source_dir="examples/3d_game_demo",
        mode="3d",
        files=("run_game.py", "procedural_art.py"),
        headless=True,
    ),
    FixtureSpec(
        name="multiplayer-game",
        source_dir="examples/multiplayer_game_demo",
        mode="2d",
        files=("run_game.py",),
    ),
)


def _host_target() -> ExportTarget:
    if sys.platform.startswith("win"):
        return ExportTarget.WINDOWS
    if sys.platform == "darwin":
        return ExportTarget.MACOS
    return ExportTarget.LINUX


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fingerprint(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _manifest_text(spec: FixtureSpec) -> str:
    include = ["assets", "config", "scenes", *spec.files]
    include_toml = ", ".join(json.dumps(value) for value in include)
    environment = ""
    if spec.headless:
        environment = '\n[run.environment]\nSWIR_GAME_DEMO_HEADLESS = "1"\n'
    return f'''name = "SwirEngine Real Game Gate — {spec.name}"
mode = "{spec.mode}"
entrypoint = "run_game.py"

[content]
include = [{include_toml}]
{environment}
[scenes]
boot = "title"

[scenes.registry.title]
path = "scenes/title.swirscene"

[scenes.registry.gameplay]
path = "scenes/gameplay.swirscene"
depends_on = ["title"]

[[content.build.nodes]]
name = "asset:fixture"
kind = "asset"
path = "assets/fixture.txt"
load = "preload"

[[content.build.nodes]]
name = "scene:title"
kind = "scene"
path = "scenes/title.swirscene"
load = "preload"
depends_on = ["asset:fixture"]

[[content.build.nodes]]
name = "scene:gameplay"
kind = "scene"
path = "scenes/gameplay.swirscene"
load = "stream"
depends_on = ["scene:title"]
'''


def _prepare_project(repository: Path, destination: Path, spec: FixtureSpec) -> None:
    source = repository / spec.source_dir
    if not source.is_dir():
        raise FileNotFoundError(f"missing source fixture directory: {source}")
    destination.mkdir(parents=True)
    (destination / "assets").mkdir()
    (destination / "scenes").mkdir()

    for relative in spec.files:
        source_file = source / relative
        if not source_file.is_file():
            raise FileNotFoundError(f"missing source fixture file: {source_file}")
        shutil.copy2(source_file, destination / relative)

    (destination / "assets" / "fixture.txt").write_text(
        f"SwirEngine 1.9 real-game production gate: {spec.name}\n",
        encoding="utf-8",
    )
    serializer = SceneSerializer()
    title = Scene()
    title.add(Rectangle2D(0, 0, 320, 90, name="production-gate-title"))
    gameplay = Scene()
    gameplay.add(Rectangle2D(32, 48, 24, 24, name="production-gate-player"))
    serializer.dump_scene(title, destination / "scenes" / "title.swirscene")
    serializer.dump_scene(gameplay, destination / "scenes" / "gameplay.swirscene")
    (destination / "swirproject.toml").write_text(_manifest_text(spec), encoding="utf-8")

    defaults = ProjectShippingDefaults.load(destination)
    defaults.write_templates()


def _validate_project(
    project_root: Path,
) -> tuple[ProjectManifest, ScenePackageRegistry, ContentBuildGraph, ProjectShippingDefaults]:
    manifest = ProjectManifest.load(project_root)

    defaults = ProjectShippingDefaults.load(project_root)
    defaults.actions.require_actions(REQUIRED_UI_ACTIONS)
    if defaults.input_source is None or defaults.settings_source is None:
        raise RuntimeError("real-game fixture did not materialize shipping input/settings defaults")

    registry = ScenePackageRegistry.load_optional(manifest)
    if registry is None:
        raise RuntimeError("real-game fixture did not activate [scenes]")
    serializer = SceneSerializer()
    diagnostics = registry.validate_documents(serializer)
    if diagnostics:
        raise RuntimeError(f"scene package diagnostics: {diagnostics!r}")

    runtime_scene = Scene()
    loader = ScenePackageLoader(registry, serializer)
    loader.transition_to_boot(runtime_scene)
    loader.transition(runtime_scene, "gameplay")

    graph = ContentBuildGraph.load_optional(manifest)
    if graph is None:
        raise RuntimeError("real-game fixture did not activate [content.build]")
    content_diagnostics = graph.diagnostics()
    if content_diagnostics:
        raise RuntimeError(f"content build diagnostics: {content_diagnostics!r}")
    plan = graph.plan(["scene:gameplay"])
    if plan.ordered_nodes != ("asset:fixture", "scene:title", "scene:gameplay"):
        raise RuntimeError(f"unexpected content dependency order: {plan.ordered_nodes!r}")
    return manifest, registry, graph, defaults


def _validate_player_state(
    manifest: ProjectManifest,
    defaults: ProjectShippingDefaults,
    user_data_root: Path,
    spec: FixtureSpec,
) -> tuple[str, str, str]:
    policy = SaveProductionPolicy(
        autosave_keep=2,
        autosave_interval_seconds=0.0,
        max_manual_slots=2,
        max_workers=1,
    )
    with ProductionGameStateSession.for_project(
        manifest,
        user_data_root=user_data_root,
        policy=policy,
    ) as session:
        input_store = InputOverrideStore(
            defaults.actions,
            session.profile_directory / "config" / "input-overrides.json",
        )
        player_actions = defaults.actions.replace_action(
            "pause",
            (
                InputBinding("key", "p"),
                InputBinding("gamepad_button", "START"),
            ),
        )
        input_store.save(player_actions)
        loaded_actions = input_store.load()
        if loaded_actions.fingerprint != player_actions.fingerprint:
            raise RuntimeError("shipping input override round-trip changed the action map")

        player_settings = defaults.settings.with_accessibility(
            reduced_motion=True,
            subtitles=False,
        )
        settings_store = session.settings_store(defaults.settings)
        settings_store.save(player_settings)
        loaded_settings = settings_store.load()
        if loaded_settings.fingerprint != player_settings.fingerprint:
            raise RuntimeError("shipping settings round-trip changed the player settings")

        snapshot = {
            "fixture": spec.name,
            "mode": spec.mode,
            "scene": "gameplay",
            "checkpoint": 1,
        }
        request_id = session.submit_manual(
            "production-gate",
            snapshot,
            metadata={"source": "real-game-production-gate"},
        )
        outcomes = session.run_until_idle(timeout=5.0)
        if len(outcomes) != 1 or outcomes[0].request_id != request_id or not outcomes[0].successful:
            raise RuntimeError("production save pipeline did not complete the fixture snapshot")
        loaded_save = session.load("production-gate")
        if dict(loaded_save.data) != snapshot:
            raise RuntimeError("production save round-trip changed the fixture snapshot")
        if loaded_save.metadata.get("source") != "real-game-production-gate":
            raise RuntimeError("production save round-trip lost fixture metadata")

        state_payload = {
            "input_fingerprint": loaded_actions.fingerprint,
            "settings_fingerprint": loaded_settings.fingerprint,
            "save": dict(loaded_save.data),
            "save_kind": loaded_save.metadata.get("save_kind"),
            "save_source": loaded_save.metadata.get("source"),
        }
        return (
            loaded_actions.fingerprint,
            loaded_settings.fingerprint,
            _fingerprint(state_payload),
        )


def _run_entrypoint(root: Path, spec: FixtureSpec) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
    if spec.headless:
        environment["SWIR_GAME_DEMO_HEADLESS"] = "1"
    return subprocess.run(
        [sys.executable, "run_game.py"],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _require_runtime_ok(result: subprocess.CompletedProcess[str], *, label: str) -> None:
    if result.returncode == 0:
        return
    stdout = result.stdout[-4000:]
    stderr = result.stderr[-4000:]
    raise RuntimeError(
        f"{label} failed with exit code {result.returncode}\nstdout:\n{stdout}\nstderr:\n{stderr}"
    )


def _verify_fixture(
    repository: Path,
    workspace: Path,
    spec: FixtureSpec,
    *,
    run_runtime: bool,
) -> FixtureReport:
    project_root = workspace / spec.name
    export_root = workspace / f"{spec.name}-staged"
    user_data_root = workspace / "user-data" / spec.name
    _prepare_project(repository, project_root, spec)
    manifest, registry, graph, defaults = _validate_project(project_root)
    input_fingerprint, settings_fingerprint, game_state_fingerprint = _validate_player_state(
        manifest,
        defaults,
        user_data_root,
        spec,
    )

    helper_files = tuple(value for value in spec.files if value != "run_game.py")
    profile = PackagingProfile(
        name=f"real-game-{spec.name}",
        target=_host_target(),
        entrypoint="run_game.py",
        include=("assets", "config", *helper_files),
        console=True,
    )
    exporter = ProjectExporter(project_root)
    plan_a = exporter.plan(profile, export_root)
    plan_b = exporter.plan(profile, export_root)
    if plan_a.files != plan_b.files:
        raise RuntimeError(f"non-deterministic export plan for {spec.name}")
    result = exporter.export(profile, export_root)

    expected = {
        "run_game.py",
        "swirproject.toml",
        "assets/fixture.txt",
        "config/controls.json",
        "config/settings.json",
        "scenes/title.swirscene",
        "scenes/gameplay.swirscene",
        *helper_files,
    }
    exported = {path.relative_to(result.output_dir).as_posix() for path in result.copied_files}
    missing = sorted(expected - exported)
    if missing:
        raise RuntimeError(f"staged {spec.name} fixture is missing required files: {missing}")
    if any(path.startswith("user-data/") for path in exported):
        raise RuntimeError("player user-data must never be staged as project shipping content")

    manifest_data = json.loads(result.manifest.read_text(encoding="utf-8"))
    manifest_hashes = manifest_data.get("sha256")
    if not isinstance(manifest_hashes, dict):
        raise TypeError("export manifest does not contain a sha256 map")
    missing_hashes = sorted(expected - set(manifest_hashes))
    if missing_hashes:
        raise RuntimeError(f"export manifest is missing required checksums: {missing_hashes}")

    source_ok: bool | None = None
    staged_ok: bool | None = None
    if run_runtime:
        source_result = _run_entrypoint(project_root, spec)
        _require_runtime_ok(source_result, label=f"{spec.name} source runtime")
        source_ok = True
        staged_result = _run_entrypoint(result.output_dir, spec)
        _require_runtime_ok(staged_result, label=f"{spec.name} staged runtime")
        staged_ok = True

    exported_files = tuple(sorted(exported))
    payload = {
        "name": spec.name,
        "mode": spec.mode,
        "source_files": spec.files,
        "exported_files": exported_files,
        "scene_fingerprint": registry.fingerprint,
        "content_fingerprint": graph.fingerprint,
        "input_fingerprint": input_fingerprint,
        "settings_fingerprint": settings_fingerprint,
        "game_state_fingerprint": game_state_fingerprint,
        "export_manifest_sha256": _sha256(result.manifest),
        "source_runtime_ok": source_ok,
        "staged_runtime_ok": staged_ok,
    }
    return FixtureReport(**payload, fingerprint=_fingerprint(payload))


def run_production_gate(
    repository: Path,
    workspace: Path,
    *,
    run_runtime: bool = True,
) -> dict[str, object]:
    repository = repository.resolve()
    reports = tuple(
        _verify_fixture(repository, workspace, spec, run_runtime=run_runtime) for spec in FIXTURES
    )
    aggregate_payload = [asdict(report) for report in reports]
    return {
        "status": "ok",
        "scope": "SwirEngine 1.9 Real-Game Production Gate",
        "runtime_validation": run_runtime,
        "fixture_count": len(reports),
        "fixtures": aggregate_payload,
        "fingerprint": _fingerprint(aggregate_payload),
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
        help="validate production staging without launching source/staged entrypoints",
    )
    args = parser.parse_args()

    with TemporaryDirectory(prefix="swirengine-real-game-1-9-") as directory:
        report = run_production_gate(
            args.repository,
            Path(directory),
            run_runtime=not args.staging_only,
        )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
