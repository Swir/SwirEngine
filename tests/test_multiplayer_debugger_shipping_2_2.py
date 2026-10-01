from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from itertools import count
from pathlib import Path

import pytest

import swirengine
from swirengine.desktop_shipping19 import create_desktop_shipping_plan
from swirengine.editor_multiplayer_debugger22 import EditorMultiplayerDebugger22
from swirengine.exporting import ExportTarget, PackagingProfile, ProjectExporter
from swirengine.multiplayer20 import MultiplayerCompatibility, ProductionMultiplayerSession
from swirengine.project19 import ProjectManifest

_RUNTIME_ENTRYPOINT = (
    r"""
import json
from pathlib import Path

import swirengine
from swirengine.multiplayer20 import MultiplayerCompatibility, ProductionMultiplayerSession
from swirengine.multiplayer_debugger22 import MultiplayerDebugger22
from swirengine.network_latency22 import NetworkRoundTripProbe22

compatibility = MultiplayerCompatibility(
    project_id="runtime-private-project",
    protocol_version="2.2",
    build_id="runtime-private-build",
    replication_schema="runtime-private-schema",
    content_fingerprint="runtime-private-content",
)
session = ProductionMultiplayerSession(
    "runtime-private-session",
    "runtime-private-host",
    compatibility,
    token_factory=lambda: "runtime-private-token-0001",
)
clock = [100.0]
probe = NetworkRoundTripProbe22(
    clock=lambda: clock[0],
    nonce_factory=lambda: "runtime-private-nonce-0001",
)
ping = probe.create_ping()
clock[0] += 0.014
probe.accept_pong(probe.reply_to_ping(ping))
debugger = MultiplayerDebugger22(session)
debugger.sample_peer(
    "runtime-private-host",
    1,
    sent_bytes=120,
    received_bytes=80,
    replicated_entities=3,
    entity_budget=6,
    round_trip_probe=probe,
)
encoded = debugger.capture_json()
capture = json.loads(encoded)
forbidden = (
    "runtime-private-project",
    "runtime-private-build",
    "runtime-private-schema",
    "runtime-private-content",
    "runtime-private-session",
    "runtime-private-host",
    "runtime-private-token",
    "runtime-private-nonce",
)
print(json.dumps({
    "engine_path": str(Path(swirengine.__file__).resolve()),
    "leak_free": all(value not in encoded for value in forbidden),
    "peer": capture["peers"][0]["alias"],
    "sent_bytes": capture["peers"][0]["samples"][0]["counters"]["traffic.sent_bytes"],
    "round_trip_ms": capture["peers"][0]["round_trip"]["latest_ms"],
    "capture_bytes": len(encoded.encode("ascii")),
}, sort_keys=True))
""".strip()
    + "\n"
)


def _compatibility() -> MultiplayerCompatibility:
    return MultiplayerCompatibility(
        project_id="authoring-private-project",
        protocol_version="2.2",
        build_id="authoring-private-build",
        replication_schema="authoring-private-schema",
        content_fingerprint="authoring-private-content",
    )


def _session() -> ProductionMultiplayerSession:
    tokens = count()
    session = ProductionMultiplayerSession(
        "authoring-private-session",
        "authoring-private-host",
        _compatibility(),
        token_factory=lambda: f"authoring-private-token-{next(tokens):04d}",
    )
    session.set_authoritative_player_state(
        "authoring-private-host",
        {"display_name": "authoring-private-state", "score": 9},
    )
    return session


def _project(root: Path, *, entrypoint: str = "print('shipping')\n") -> Path:
    root.mkdir()
    (root / "main.py").write_text(entrypoint, encoding="ascii")
    assets = root / "assets"
    assets.mkdir()
    (assets / "marker.txt").write_text("runtime-asset\n", encoding="ascii")
    return root


def _assert_no_editor_only_files(paths: tuple[Path, ...] | list[Path]) -> None:
    assert all(not path.parts or path.parts[0].casefold() != ".swir" for path in paths)


def test_desktop_shipping_plan_keeps_source_canonicalization_bounded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _project(tmp_path / "bounded-planning")
    assets = root / "assets"
    for index in range(32):
        (assets / f"asset-{index:02d}.bin").write_bytes(f"asset-{index}".encode("ascii"))
    (root / "swirproject.toml").write_text(
        """
name = "Bounded Shipping"
mode = "2d"
entrypoint = "main.py"

[content]
include = ["assets"]

[profiles.linux]
target = "linux"
app_name = "BoundedShipping"
include = ["assets"]
onefile = false
console = true
""".strip()
        + "\n",
        encoding="ascii",
    )
    manifest = ProjectManifest.load(root)
    original_resolve = Path.resolve
    resolve_calls = 0

    def counted_resolve(path: Path, *args: object, **kwargs: object) -> Path:
        nonlocal resolve_calls
        resolve_calls += 1
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", counted_resolve)

    plan = create_desktop_shipping_plan(manifest, "linux")

    assert len(plan.source_inventory) == 35
    assert resolve_calls <= 80


def test_source_swap_after_discovery_is_rejected_before_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _project(tmp_path / "project")
    source = root / "assets" / "marker.txt"
    outside = tmp_path / "outside-secret.txt"
    outside.write_text("private-outside-source", encoding="ascii")
    probe = root / "symlink-probe"
    try:
        probe.symlink_to(outside)
    except OSError:
        pytest.skip("file symlinks are unavailable on this runner")
    probe.unlink()
    output = tmp_path / "out"
    output.mkdir()
    sentinel = output / "sentinel.txt"
    sentinel.write_text("keep", encoding="ascii")
    exporter = ProjectExporter(root)
    original_included_files = exporter._included_files
    swapped = False

    def swap_after_discovery(
        relative: Path,
        *,
        exclude: object,
        output_dir: Path,
        output_relative: Path | None,
    ) -> tuple[Path, ...]:
        nonlocal swapped
        files = original_included_files(
            relative,
            exclude=exclude,
            output_dir=output_dir,
            output_relative=output_relative,
        )
        if not swapped and Path("assets/marker.txt") in files:
            source.unlink()
            source.symlink_to(outside)
            swapped = True
        return files

    monkeypatch.setattr(exporter, "_included_files", swap_after_discovery)

    with pytest.raises(ValueError, match="resolve inside the project"):
        exporter.export(PackagingProfile(include=(".",), exclude=()), output)

    assert sentinel.read_text(encoding="ascii") == "keep"


def test_source_swap_after_plan_is_rejected_before_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _project(tmp_path / "project")
    source = root / "assets" / "marker.txt"
    outside = tmp_path / "outside-secret.txt"
    outside.write_text("private-outside-source", encoding="ascii")
    probe = root / "symlink-probe"
    try:
        probe.symlink_to(outside)
    except OSError:
        pytest.skip("file symlinks are unavailable on this runner")
    probe.unlink()
    output = tmp_path / "out"
    output.mkdir()
    sentinel = output / "sentinel.txt"
    sentinel.write_text("keep", encoding="ascii")
    exporter = ProjectExporter(root)
    profile = PackagingProfile(include=(".",), exclude=())
    safe_plan = exporter.plan(profile, output)

    def swapped_plan(
        _profile: PackagingProfile,
        _output_dir: str | Path | None = None,
    ) -> object:
        source.unlink()
        source.symlink_to(outside)
        return safe_plan

    monkeypatch.setattr(exporter, "plan", swapped_plan)

    with pytest.raises(ValueError, match="resolve inside the project"):
        exporter.export(profile, output)

    assert sentinel.read_text(encoding="ascii") == "keep"


def test_privacy_safe_capture_is_never_shipped_by_a_broad_desktop_profile(
    tmp_path: Path,
) -> None:
    root = _project(tmp_path / "project")
    controller = EditorMultiplayerDebugger22(root)
    controller.attach(_session())
    controller.sample(
        "authoring-private-host",
        1,
        sent_bytes=77,
        received_bytes=55,
        replicated_entities=2,
    )
    capture = controller.export_capture()
    capture_payload = capture.read_text(encoding="ascii")
    assert "authoring-private-host" not in capture_payload
    assert "authoring-private-session" not in capture_payload
    assert "authoring-private-token" not in capture_payload
    assert "authoring-private-state" not in capture_payload
    (root / ".swir" / "editor-session.json").write_text(
        "authoring-private-editor-state",
        encoding="ascii",
    )

    profile = PackagingProfile(
        name="broad",
        target=ExportTarget.LINUX,
        include=(".",),
        exclude=(),
    )
    exporter = ProjectExporter(root)
    plan = exporter.plan(profile, tmp_path / "export")
    _assert_no_editor_only_files(list(plan.files))

    result = exporter.export(profile, tmp_path / "export")
    manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
    _assert_no_editor_only_files([Path(value) for value in manifest["files"]])
    assert result.native_spec is not None
    spec = result.native_spec.read_text(encoding="utf-8")
    assert ".swir" not in spec.casefold()
    assert not (result.output_dir / ".swir").exists()
    assert not any(
        "authoring-private-editor-state" in path.read_text(encoding="utf-8")
        for path in result.output_dir.rglob("*")
        if path.is_file()
    )


@pytest.mark.parametrize(
    "include",
    [
        (".",),
        ("",),
        (".swir", "."),
        (".swir/multiplayer-debugger/capture.json", "assets"),
    ],
)
def test_editor_only_root_cannot_be_reincluded_by_profile_shape(
    tmp_path: Path,
    include: tuple[str, ...],
) -> None:
    root = _project(tmp_path / "project")
    editor = root / ".swir" / "multiplayer-debugger"
    editor.mkdir(parents=True)
    (editor / "capture.json").write_text("private-capture", encoding="ascii")

    plan = ProjectExporter(root).plan(
        PackagingProfile(include=include, exclude=()),
        tmp_path / "out",
    )

    _assert_no_editor_only_files(list(plan.files))
    assert Path("main.py") in plan.files


def test_editor_only_root_is_blocked_case_insensitively(tmp_path: Path) -> None:
    root = _project(tmp_path / "project")
    editor = root / ".SWIR"
    editor.mkdir()
    (editor / "private.json").write_text("private-casefold-capture", encoding="ascii")

    result = ProjectExporter(root).export(
        PackagingProfile(include=(".",), exclude=()),
        tmp_path / "out",
    )

    assert not (result.output_dir / ".SWIR").exists()
    assert "private-casefold-capture" not in result.manifest.read_text(encoding="utf-8")


def test_editor_only_directory_symlink_is_not_followed_or_shipped(tmp_path: Path) -> None:
    root = _project(tmp_path / "project")
    outside = tmp_path / "outside-editor-state"
    outside.mkdir()
    (outside / "capture.json").write_text("private-outside-capture", encoding="ascii")
    editor_link = root / ".swir"
    try:
        editor_link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable on this runner")

    result = ProjectExporter(root).export(
        PackagingProfile(include=(".",), exclude=()),
        tmp_path / "out",
    )

    assert not (result.output_dir / ".swir").exists()
    assert "private-outside-capture" not in result.manifest.read_text(encoding="utf-8")
    assert (outside / "capture.json").read_text(encoding="ascii") == "private-outside-capture"


def test_editor_only_file_alias_fails_before_previous_output_is_cleaned(
    tmp_path: Path,
) -> None:
    root = _project(tmp_path / "project")
    editor = root / ".swir"
    editor.mkdir()
    private = editor / "capture.json"
    private.write_text("private-editor-capture", encoding="ascii")
    alias = root / "assets" / "capture-alias.json"
    try:
        alias.symlink_to(private)
    except OSError:
        pytest.skip("file symlinks are unavailable on this runner")
    output = tmp_path / "out"
    output.mkdir()
    sentinel = output / "sentinel.txt"
    sentinel.write_text("keep", encoding="ascii")

    with pytest.raises(ValueError, match="editor-only \\.swir"):
        ProjectExporter(root).export(
            PackagingProfile(target=ExportTarget.WEB, include=(".",), exclude=()),
            output,
        )

    assert sentinel.read_text(encoding="ascii") == "keep"
    assert not (output / "assets" / "capture-alias.json").exists()


@pytest.mark.parametrize("kind", ("entrypoint", "icon"))
def test_editor_only_entrypoint_and_icon_aliases_fail_before_cleanup(
    tmp_path: Path,
    kind: str,
) -> None:
    root = _project(tmp_path / "project")
    editor = root / ".SwIr"
    editor.mkdir()
    if kind == "entrypoint":
        private = editor / "private-main.py"
        private.write_text("print('private')\n", encoding="ascii")
        alias = root / "launch.py"
        profile = PackagingProfile(
            target=ExportTarget.WEB,
            entrypoint="launch.py",
            include=(),
            exclude=(),
        )
    else:
        private = editor / "private.ico"
        private.write_bytes(b"private-icon")
        alias = root / "game.ico"
        profile = PackagingProfile(
            target=ExportTarget.LINUX,
            icon="game.ico",
            include=(),
            exclude=(),
        )
    try:
        alias.symlink_to(private)
    except OSError:
        pytest.skip("file symlinks are unavailable on this runner")
    output = tmp_path / "out"
    output.mkdir()
    sentinel = output / "sentinel.txt"
    sentinel.write_text("keep", encoding="ascii")

    with pytest.raises(ValueError, match="editor-only \\.swir"):
        ProjectExporter(root).export(profile, output)

    assert sentinel.read_text(encoding="ascii") == "keep"


def test_direct_include_alias_to_editor_only_directory_fails_before_cleanup(
    tmp_path: Path,
) -> None:
    root = _project(tmp_path / "project")
    editor = root / ".swir"
    editor.mkdir()
    (editor / "capture.json").write_text("private-capture", encoding="ascii")
    alias = root / "private-data"
    try:
        alias.symlink_to(editor, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable on this runner")
    output = tmp_path / "out"
    output.mkdir()
    sentinel = output / "sentinel.txt"
    sentinel.write_text("keep", encoding="ascii")

    with pytest.raises(ValueError, match="editor-only \\.swir"):
        ProjectExporter(root).export(
            PackagingProfile(
                target=ExportTarget.WEB,
                include=("private-data",),
                exclude=(),
            ),
            output,
        )

    assert sentinel.read_text(encoding="ascii") == "keep"


@pytest.mark.skipif(os.name != "nt", reason="Win32 normalizes trailing dots in path components")
def test_windows_trailing_dot_alias_cannot_reinclude_editor_only_root(
    tmp_path: Path,
) -> None:
    root = _project(tmp_path / "project")
    editor = root / ".swir"
    editor.mkdir()
    (editor / "capture.json").write_text("private-capture", encoding="ascii")
    output = tmp_path / "out"
    output.mkdir()
    sentinel = output / "sentinel.txt"
    sentinel.write_text("keep", encoding="ascii")

    with pytest.raises(ValueError, match="editor-only \\.swir"):
        ProjectExporter(root).export(
            PackagingProfile(
                target=ExportTarget.WEB,
                include=(".SWIR.",),
                exclude=(),
            ),
            output,
        )

    assert sentinel.read_text(encoding="ascii") == "keep"


def test_unsafe_source_symlink_fails_before_previous_output_is_cleaned(tmp_path: Path) -> None:
    root = _project(tmp_path / "project")
    outside = tmp_path / "outside-secret.bin"
    outside.write_bytes(b"private-outside-source")
    link = root / "assets" / "linked.bin"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("file symlinks are unavailable on this runner")
    output = tmp_path / "out"
    output.mkdir()
    sentinel = output / "sentinel.txt"
    sentinel.write_text("keep", encoding="ascii")

    with pytest.raises(ValueError, match="resolve inside the project"):
        ProjectExporter(root).export(
            PackagingProfile(include=(".",), exclude=()),
            output,
        )

    assert sentinel.read_text(encoding="ascii") == "keep"
    assert not (output / "assets" / "linked.bin").exists()


def test_repeated_broad_default_export_ignores_only_its_exact_output_subtree(
    tmp_path: Path,
) -> None:
    root = _project(tmp_path / "project")
    profile = PackagingProfile(
        name="broad-repeat",
        target=ExportTarget.WEB,
        include=(".",),
        exclude=(),
    )
    exporter = ProjectExporter(root)
    first = exporter.export(profile)
    own_output = first.output_dir.relative_to(root)
    (first.output_dir / "previous-only.txt").write_text("old", encoding="ascii")
    sibling = root / "dist" / "sibling-export" / "keep.txt"
    sibling.parent.mkdir(parents=True)
    sibling.write_text("sibling", encoding="ascii")

    plan = exporter.plan(profile)

    assert all(path != own_output and own_output not in path.parents for path in plan.files)
    assert Path("dist/sibling-export/keep.txt") in plan.files
    second = exporter.export(profile)
    manifest = json.loads(second.manifest.read_text(encoding="utf-8"))
    shipped = tuple(Path(value) for value in manifest["files"])
    assert all(path != own_output and own_output not in path.parents for path in shipped)
    assert (second.output_dir / "dist" / "sibling-export" / "keep.txt").read_text(
        encoding="ascii"
    ) == "sibling"

    # A later unsafe source must still fail before cleaning the last known-good output.
    sentinel = second.output_dir / "sentinel.txt"
    sentinel.write_text("keep", encoding="ascii")
    invalid = PackagingProfile(
        name=profile.name,
        target=profile.target,
        include=("../outside",),
        exclude=(),
    )

    with pytest.raises(ValueError, match="stay inside the project"):
        exporter.export(invalid)

    assert sentinel.read_text(encoding="ascii") == "keep"


def test_broad_plan_ignores_project_alias_to_exact_external_output(tmp_path: Path) -> None:
    root = _project(tmp_path / "project")
    output = tmp_path / "external-output"
    output.mkdir()
    (output / "previous.txt").write_text("previous-output", encoding="ascii")
    alias = root / "export-alias"
    try:
        alias.symlink_to(output, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable on this runner")

    plan = ProjectExporter(root).plan(
        PackagingProfile(target=ExportTarget.WEB, include=(".",), exclude=()),
        output,
    )

    assert all(path != Path("export-alias") and Path("export-alias") not in path.parents for path in plan.files)
    assert (output / "previous.txt").read_text(encoding="ascii") == "previous-output"


@pytest.mark.skipif(os.name != "nt", reason="junctions are a Windows path type")
def test_broad_plan_does_not_scan_exact_output_junction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _project(tmp_path / "project")
    output = tmp_path / "external-output"
    output.mkdir()
    (output / "previous.txt").write_text("previous-output", encoding="ascii")
    alias = root / "export-junction"
    created = subprocess.run(
        ("cmd", "/c", "mklink", "/J", str(alias), str(output)),
        check=False,
        capture_output=True,
        text=True,
    )
    if created.returncode != 0:
        pytest.skip("directory junctions are unavailable on this runner")
    original_scandir = os.scandir

    def reject_output_scan(path: str | os.PathLike[str]) -> object:
        if Path(path) == alias:
            raise AssertionError("the exact output junction must be pruned before scandir")
        return original_scandir(path)

    monkeypatch.setattr(os, "scandir", reject_output_scan)

    plan = ProjectExporter(root).plan(
        PackagingProfile(target=ExportTarget.WEB, include=(".",), exclude=()),
        output,
    )

    assert all(path != Path("export-junction") for path in plan.files)
    assert (output / "previous.txt").read_text(encoding="ascii") == "previous-output"


@pytest.mark.parametrize(
    "profile",
    [
        PackagingProfile(entrypoint=".swir/main.py", include=(".",), exclude=()),
        PackagingProfile(include=("../outside",), exclude=()),
    ],
)
def test_editor_entrypoint_and_traversal_fail_before_output_cleanup(
    tmp_path: Path,
    profile: PackagingProfile,
) -> None:
    root = _project(tmp_path / "project")
    editor = root / ".swir"
    editor.mkdir()
    (editor / "main.py").write_text("print('editor only')\n", encoding="ascii")
    output = tmp_path / "out"
    output.mkdir()
    sentinel = output / "sentinel.txt"
    sentinel.write_text("keep", encoding="ascii")

    with pytest.raises(ValueError):
        ProjectExporter(root).export(profile, output)

    assert sentinel.read_text(encoding="ascii") == "keep"


def test_relocated_export_runs_debugger_and_real_round_trip_from_installed_engine(
    tmp_path: Path,
) -> None:
    root = _project(tmp_path / "runtime-project", entrypoint=_RUNTIME_ENTRYPOINT)
    editor = root / ".swir"
    editor.mkdir()
    (editor / "capture.json").write_text("runtime-private-editor-capture", encoding="ascii")
    exported = ProjectExporter(root).export(
        PackagingProfile(include=(".",), exclude=(), target=ExportTarget.WEB),
        tmp_path / "staged",
    )
    relocated = tmp_path / "relocated"
    shutil.move(str(exported.output_dir), relocated)
    root.rename(tmp_path / "authoring-unavailable")

    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    isolated = env.get("SWIR_MULTIPLAYER_DEBUGGER_INSTALLED_ONLY") == "1"
    if not isolated:
        env["PYTHONPATH"] = str(Path(swirengine.__file__).resolve().parent.parent)
    completed = subprocess.run(
        [sys.executable, *(["-I"] if isolated else []), str(relocated / "main.py")],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
        check=True,
    )
    report = json.loads(completed.stdout.strip().splitlines()[-1])

    assert report["leak_free"] is True
    assert report["peer"] == "peer-000"
    assert report["sent_bytes"] == 120
    assert report["round_trip_ms"] == pytest.approx(14.0)
    assert report["capture_bytes"] <= 2 * 1024 * 1024
    assert not (relocated / ".swir").exists()
    if isolated:
        assert "site-packages" in Path(report["engine_path"]).parts
        assert not Path(report["engine_path"]).is_relative_to(Path(__file__).resolve().parents[1])
