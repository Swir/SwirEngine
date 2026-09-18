from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from swirengine.desktop_shipping19 import (
    DesktopShippingError,
    DesktopShippingManifest,
    DesktopShippingPlan,
    ShippingInventoryEntry,
    build_desktop_shipping,
    canonical_desktop_target,
    create_desktop_shipping_plan,
    verify_desktop_shipping,
)
from swirengine.exporting import ExportTarget
from swirengine.project19 import ProjectManifest


def _project(root: Path, *, target: str = "linux") -> ProjectManifest:
    root.mkdir()
    (root / "main.py").write_text("print('shipping')\n", encoding="utf-8")
    assets = root / "assets"
    assets.mkdir()
    (assets / "payload.bin").write_bytes(b"swir-shipping")
    (root / "swirproject.toml").write_text(
        f"""
name = "Shipping Demo"
mode = "2d"
entrypoint = "main.py"

[content]
include = ["assets"]

[profiles.native]
target = "{target}"
app_name = "ShippingDemo"
include = ["assets"]
onefile = false
console = true
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return ProjectManifest.load(root)


def test_canonical_desktop_target_maps_only_supported_hosts() -> None:
    assert canonical_desktop_target("win32") is ExportTarget.WINDOWS
    assert canonical_desktop_target("linux") is ExportTarget.LINUX
    assert canonical_desktop_target("linux-musl") is ExportTarget.LINUX
    assert canonical_desktop_target("darwin") is ExportTarget.MACOS
    with pytest.raises(DesktopShippingError, match="unsupported desktop build host"):
        canonical_desktop_target("freebsd14")


def test_plan_is_checkout_independent_and_source_sensitive(tmp_path: Path) -> None:
    first = _project(tmp_path / "first")
    second = _project(tmp_path / "second")

    first_plan = create_desktop_shipping_plan(first, "native")
    second_plan = create_desktop_shipping_plan(second, "native")

    assert first_plan.fingerprint == second_plan.fingerprint
    assert first_plan.portable() == second_plan.portable()
    assert [entry.path for entry in first_plan.source_inventory] == [
        "assets/payload.bin",
        "main.py",
        "swirproject.toml",
    ]

    (second.root / "assets" / "payload.bin").write_bytes(b"changed")
    changed = create_desktop_shipping_plan(ProjectManifest.load(second.root), "native")
    assert changed.fingerprint != first_plan.fingerprint


def test_plan_json_round_trip_and_typed_booleans(tmp_path: Path) -> None:
    plan = create_desktop_shipping_plan(_project(tmp_path / "project"), "native")
    path = plan.write(tmp_path / "plan.json")

    loaded = DesktopShippingPlan.load(path)
    assert loaded == plan
    assert loaded.fingerprint == plan.fingerprint

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["profile"]["onefile"] = "false"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(DesktopShippingError, match="missing required fields"):
        DesktopShippingPlan.load(path)


def test_plan_rejects_non_desktop_profile(tmp_path: Path) -> None:
    manifest = _project(tmp_path / "project")
    text = manifest.path.read_text(encoding="utf-8").replace(
        'target = "linux"', 'target = "web"'
    )
    manifest.path.write_text(text, encoding="utf-8")

    with pytest.raises(DesktopShippingError, match="desktop shipping requires"):
        create_desktop_shipping_plan(ProjectManifest.load(manifest.root), "native")


def test_inventory_rejects_casefold_collisions() -> None:
    digest = hashlib.sha256(b"x").hexdigest()
    first = ShippingInventoryEntry("Data/File.bin", "file", 1, digest)
    second = ShippingInventoryEntry("data/file.bin", "file", 1, digest)

    with pytest.raises(DesktopShippingError, match="case-folded path collisions"):
        DesktopShippingPlan(
            project_name="Demo",
            project_fingerprint="project",
            profile_name="native",
            target=ExportTarget.LINUX,
            app_name="Demo",
            entrypoint="main.py",
            onefile=False,
            console=True,
            source_inventory=(first, second),
        )


def test_plan_rejects_symlinked_source_escape(tmp_path: Path) -> None:
    manifest = _project(tmp_path / "project")
    external = tmp_path / "outside.bin"
    external.write_bytes(b"secret")
    link = manifest.root / "assets" / "linked.bin"
    try:
        link.symlink_to(external)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is unavailable on this host")

    with pytest.raises(DesktopShippingError, match="outside its allowed root"):
        create_desktop_shipping_plan(ProjectManifest.load(manifest.root), "native")


def test_build_rejects_cross_host_before_runner(tmp_path: Path, monkeypatch) -> None:
    manifest = _project(tmp_path / "project", target="windows")
    monkeypatch.setattr(
        "swirengine.desktop_shipping19.canonical_desktop_target",
        lambda platform=None: ExportTarget.LINUX,
    )

    with pytest.raises(DesktopShippingError, match="matching windows host"):
        build_desktop_shipping(manifest, "native", tmp_path / "out")


def test_build_writes_and_verifies_artifact_manifest(tmp_path: Path, monkeypatch) -> None:
    target = canonical_desktop_target()
    manifest = _project(tmp_path / "project", target=target.value)
    monkeypatch.setattr("swirengine.exporting.sys.platform", sys.platform)

    def runner(command, *, cwd, capture_output, text, check):
        assert capture_output is True
        assert text is True
        assert check is False
        artifact = Path(cwd) / "native-dist" / "game.bin"
        artifact.parent.mkdir(parents=True)
        artifact.write_bytes(b"native-artifact")
        return SimpleNamespace(returncode=0, stderr="")

    result = build_desktop_shipping(
        manifest,
        "native",
        tmp_path / "out",
        runner=runner,
    )

    assert result.plan_path.is_file()
    assert result.manifest_path.is_file()
    assert result.manifest.plan_fingerprint == result.plan.fingerprint
    assert result.manifest.target is target
    assert [entry.path for entry in result.manifest.artifacts] == ["game.bin"]
    assert verify_desktop_shipping(
        result.manifest_path,
        plan_path=result.plan_path,
    ) == result.manifest


def test_verify_rejects_artifact_tampering_and_unexpected_files(
    tmp_path: Path, monkeypatch
) -> None:
    target = canonical_desktop_target()
    manifest = _project(tmp_path / "project", target=target.value)
    monkeypatch.setattr("swirengine.exporting.sys.platform", sys.platform)

    def runner(command, *, cwd, capture_output, text, check):
        artifact = Path(cwd) / "native-dist" / "game.bin"
        artifact.parent.mkdir(parents=True)
        artifact.write_bytes(b"native-artifact")
        return SimpleNamespace(returncode=0, stderr="")

    result = build_desktop_shipping(manifest, "native", tmp_path / "out", runner=runner)
    artifact = result.build.export.output_dir / "native-dist" / "game.bin"
    artifact.write_bytes(b"tampered")

    with pytest.raises(DesktopShippingError, match="artifact inventory mismatch"):
        verify_desktop_shipping(result.manifest_path, plan_path=result.plan_path)

    artifact.write_bytes(b"native-artifact")
    (artifact.parent / "unexpected.bin").write_bytes(b"extra")
    with pytest.raises(DesktopShippingError, match="inventory paths changed"):
        verify_desktop_shipping(result.manifest_path, plan_path=result.plan_path)


def test_manifest_rejects_cross_build_claim_and_invalid_digest() -> None:
    digest = hashlib.sha256(b"artifact").hexdigest()
    entry = ShippingInventoryEntry("game.bin", "file", 8, digest)

    with pytest.raises(DesktopShippingError, match="host must match target"):
        DesktopShippingManifest(
            plan_fingerprint="0" * 64,
            target=ExportTarget.WINDOWS,
            host="linux",
            python="3.13",
            artifact_root="native-dist",
            artifacts=(entry,),
        )
    with pytest.raises(DesktopShippingError, match="plan fingerprint"):
        DesktopShippingManifest(
            plan_fingerprint="invalid",
            target=ExportTarget.LINUX,
            host="linux",
            python="3.13",
            artifact_root="native-dist",
            artifacts=(entry,),
        )
