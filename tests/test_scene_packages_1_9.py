from __future__ import annotations

from pathlib import Path

import pytest

from swirengine import Color, Prefab, Rectangle2D, Scene, SceneSerializer
from swirengine.project19 import ProjectManifest
from swirengine.scene_packages19 import (
    ScenePackageError,
    ScenePackageLoader,
    ScenePackageRegistry,
)


def _project(tmp_path: Path, scenes_block: str | None) -> tuple[Path, ProjectManifest]:
    root = tmp_path
    root.mkdir(exist_ok=True)
    (root / "main.py").write_text("print('game')\n", encoding="utf-8")
    (root / "assets").mkdir(exist_ok=True)
    (root / "scripts").mkdir(exist_ok=True)
    (root / "scenes").mkdir(exist_ok=True)
    manifest = [
        'name = "Scene Shipping"',
        'mode = "2d"',
        'entrypoint = "main.py"',
        "",
        "[content]",
        'include = ["assets", "scenes", "scripts"]',
    ]
    if scenes_block:
        manifest.extend(("", scenes_block.strip()))
    (root / "swirproject.toml").write_text("\n".join(manifest) + "\n", encoding="utf-8")
    return root, ProjectManifest.load(root)


def _write_documents(root: Path) -> None:
    serializer = SceneSerializer()
    title = Scene()
    title.add(Rectangle2D(0, 0, 320, 90, color=Color(0.1, 0.7, 1.0, 1.0), name="title"))
    level = Scene()
    level.add(Rectangle2D(10, 20, 30, 40, name="level-player"))
    serializer.dump_scene(title, root / "scenes" / "title.swirscene")
    serializer.dump_scene(level, root / "scenes" / "level.swirscene")
    serializer.dump_prefab(
        Prefab(Rectangle2D(0, 0, 16, 16, name="crate"), name="crate"),
        root / "scenes" / "crate.swirprefab",
    )


SCENES = """
[scenes]
boot = "title"

[scenes.registry.title]
path = "scenes/title.swirscene"
prefabs = []
depends_on = []

[scenes.registry.level]
path = "scenes/level.swirscene"
prefabs = ["scenes/crate.swirprefab"]
depends_on = ["title"]
"""


def test_scene_registry_is_optional_for_legacy_projects(tmp_path: Path) -> None:
    _, manifest = _project(tmp_path, None)
    assert ScenePackageRegistry.load_optional(manifest) is None


def test_registry_builds_deterministic_dependency_plan(tmp_path: Path) -> None:
    root, manifest = _project(tmp_path, SCENES)
    _write_documents(root)
    registry = ScenePackageRegistry.load_optional(manifest)
    assert registry is not None

    plan = registry.plan("level")

    assert registry.boot == "title"
    assert plan.ordered_packages == ("title", "level")
    assert plan.scene_paths == ("scenes/title.swirscene", "scenes/level.swirscene")
    assert plan.prefab_paths == ("scenes/crate.swirprefab",)
    assert len(registry.fingerprint) == 64
    assert len(plan.fingerprint) == 64
    assert registry.plan("level").fingerprint == plan.fingerprint


def test_registry_fingerprint_is_independent_of_checkout_location(tmp_path: Path) -> None:
    left, left_manifest = _project(tmp_path / "left", SCENES)
    right, right_manifest = _project(tmp_path / "right", SCENES)
    _write_documents(left)
    _write_documents(right)

    left_registry = ScenePackageRegistry.load_optional(left_manifest)
    right_registry = ScenePackageRegistry.load_optional(right_manifest)
    assert left_registry is not None and right_registry is not None
    assert left_registry.fingerprint == right_registry.fingerprint


def test_registry_rejects_unknown_dependencies_and_cycles(tmp_path: Path) -> None:
    unknown = """
[scenes]
boot = "title"
[scenes.registry.title]
path = "scenes/title.swirscene"
depends_on = ["missing"]
"""
    _, manifest = _project(tmp_path / "unknown", unknown)
    with pytest.raises(ScenePackageError, match="unknown package"):
        ScenePackageRegistry.load_optional(manifest)

    cycle = """
[scenes]
boot = "a"
[scenes.registry.a]
path = "scenes/a.swirscene"
depends_on = ["b"]
[scenes.registry.b]
path = "scenes/b.swirscene"
depends_on = ["a"]
"""
    _, manifest = _project(tmp_path / "cycle", cycle)
    with pytest.raises(ScenePackageError, match="dependency cycle"):
        ScenePackageRegistry.load_optional(manifest)


@pytest.mark.parametrize("unsafe", ["../outside.swirscene", "/tmp/out.swirscene", r"C:\out.swirscene"])
def test_registry_rejects_manifest_paths_that_escape_project(tmp_path: Path, unsafe: str) -> None:
    block = f"""
[scenes]
boot = "title"
[scenes.registry.title]
path = "{unsafe.replace(chr(92), chr(92) * 2)}"
"""
    _, manifest = _project(tmp_path, block)
    with pytest.raises(ScenePackageError, match="inside the project"):
        ScenePackageRegistry.load_optional(manifest)


def test_diagnostics_find_missing_scene_and_prefab(tmp_path: Path) -> None:
    _, manifest = _project(tmp_path, SCENES)
    registry = ScenePackageRegistry.load_optional(manifest)
    assert registry is not None

    diagnostics = registry.diagnostics()
    codes = [item.code for item in diagnostics]

    assert codes.count("scene-package-missing") == 2
    assert codes.count("scene-prefab-missing") == 1


def test_document_validation_uses_explicit_serializer_contract(tmp_path: Path) -> None:
    root, manifest = _project(tmp_path, SCENES)
    _write_documents(root)
    registry = ScenePackageRegistry.load_optional(manifest)
    assert registry is not None

    assert registry.validate_documents(SceneSerializer()) == ()
    (root / "scenes" / "level.swirscene").write_text("not-json", encoding="utf-8")
    diagnostics = registry.validate_documents(SceneSerializer())
    assert any(item.code == "scene-package-invalid" for item in diagnostics)


def test_loader_transitions_existing_scene_without_replacing_its_identity(tmp_path: Path) -> None:
    root, manifest = _project(tmp_path, SCENES)
    _write_documents(root)
    registry = ScenePackageRegistry.load_optional(manifest)
    assert registry is not None
    loader = ScenePackageLoader(registry)
    scene = Scene()
    scene.add(Rectangle2D(0, 0, 1, 1, name="old"))
    scene_identity = id(scene)

    loaded = loader.transition_to_boot(scene)
    assert id(scene) == scene_identity
    assert loaded.scene is scene
    assert loader.current_name == "title"
    assert scene.find("title") is not None
    assert scene.find("old") is None

    loaded = loader.transition(scene, "level")
    assert loaded.scene is scene
    assert loader.current_name == "level"
    assert loaded.plan.ordered_packages == ("title", "level")
    assert scene.find("level-player") is not None
    assert "scenes/crate.swirprefab" in loaded.prefabs
    loaded.prefabs["scenes/crate.swirprefab"].instantiate(scene)
    assert scene.find("crate") is not None


def test_symlink_escape_is_rejected_during_runtime_resolution(tmp_path: Path) -> None:
    root, manifest = _project(tmp_path / "project", SCENES)
    _write_documents(root)
    outside = tmp_path / "outside.swirscene"
    outside.write_text("{}", encoding="utf-8")
    link = root / "scenes" / "level.swirscene"
    link.unlink()
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this runner")
    registry = ScenePackageRegistry.load_optional(manifest)
    assert registry is not None
    with pytest.raises(ScenePackageError, match="escapes project root"):
        registry.resolve_path("scenes/level.swirscene")


def test_unknown_scene_name_has_actionable_available_list(tmp_path: Path) -> None:
    root, manifest = _project(tmp_path, SCENES)
    _write_documents(root)
    registry = ScenePackageRegistry.load_optional(manifest)
    assert registry is not None
    with pytest.raises(ScenePackageError, match="available packages: level, title"):
        registry.plan("credits")
