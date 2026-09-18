from __future__ import annotations

from pathlib import Path

import pytest

from swirengine.asset_pipeline import AssetPreloader
from swirengine.asset_streaming import AssetStreamingManager
from swirengine.assets import AssetManager
from swirengine.content_build19 import (
    ContentBuildError,
    ContentBuildGraph,
    ContentBuildKind,
    ContentLoadPolicy,
)
from swirengine.project19 import ProjectManifest


def _project(tmp_path: Path, build_block: str | None) -> tuple[Path, ProjectManifest]:
    root = tmp_path
    root.mkdir(parents=True, exist_ok=True)
    (root / "main.py").write_text("print('game')\n", encoding="utf-8")
    (root / "assets").mkdir(exist_ok=True)
    (root / "scenes").mkdir(exist_ok=True)
    (root / "shaders").mkdir(exist_ok=True)
    (root / "generated").mkdir(exist_ok=True)
    manifest = [
        'name = "Content Shipping"',
        'mode = "3d"',
        'entrypoint = "main.py"',
        "",
        "[content]",
        'include = ["assets"]',
    ]
    if build_block:
        manifest.extend(("", build_block.strip()))
    (root / "swirproject.toml").write_text("\n".join(manifest) + "\n", encoding="utf-8")
    return root, ProjectManifest.load(root)


def _write_content(root: Path) -> None:
    (root / "shaders" / "world.glsl").write_text("void main() {}\n", encoding="utf-8")
    (root / "assets" / "world.bin").write_bytes(b"world")
    (root / "scenes" / "level.swirscene").write_text("{}\n", encoding="utf-8")
    (root / "generated" / "nav.bin").write_bytes(b"nav")


BUILD = """
[[content.build.nodes]]
name = "shader:world"
kind = "shader"
path = "shaders/world.glsl"

[[content.build.nodes]]
name = "asset:world"
kind = "asset"
path = "assets/world.bin"
depends_on = ["shader:world"]

[[content.build.nodes]]
name = "generated:nav"
kind = "generated"
path = "generated/nav.bin"
depends_on = ["asset:world"]

[[content.build.nodes]]
name = "scene:level"
kind = "scene"
path = "scenes/level.swirscene"
depends_on = ["generated:nav"]
"""


def test_content_build_is_optional_for_legacy_projects(tmp_path: Path) -> None:
    _, manifest = _project(tmp_path, None)
    assert ContentBuildGraph.load_optional(manifest) is None


def test_graph_builds_dependency_first_runtime_plan_with_kind_defaults(tmp_path: Path) -> None:
    root, manifest = _project(tmp_path, BUILD)
    _write_content(root)
    graph = ContentBuildGraph.load_optional(manifest)
    assert graph is not None

    plan = graph.plan(["scene:level"])

    assert plan.ordered_nodes == (
        "shader:world",
        "asset:world",
        "generated:nav",
        "scene:level",
    )
    assert plan.all_paths == (
        "shaders/world.glsl",
        "assets/world.bin",
        "generated/nav.bin",
        "scenes/level.swirscene",
    )
    assert plan.warmup_paths == ("shaders/world.glsl",)
    assert plan.preload_paths == ("assets/world.bin", "generated/nav.bin")
    assert plan.stream_paths == ("scenes/level.swirscene",)
    assert plan.generated_paths == ("generated/nav.bin",)
    assert graph.node("shader:world").kind is ContentBuildKind.SHADER
    assert graph.node("shader:world").load is ContentLoadPolicy.WARMUP
    assert graph.node("scene:level").load is ContentLoadPolicy.STREAM
    assert len(graph.fingerprint) == 64
    assert len(plan.fingerprint) == 64


def test_graph_fingerprint_is_checkout_independent(tmp_path: Path) -> None:
    left, left_manifest = _project(tmp_path / "left", BUILD)
    right, right_manifest = _project(tmp_path / "right", BUILD)
    _write_content(left)
    _write_content(right)

    left_graph = ContentBuildGraph.load_optional(left_manifest)
    right_graph = ContentBuildGraph.load_optional(right_manifest)
    assert left_graph is not None and right_graph is not None
    assert left_graph.fingerprint == right_graph.fingerprint
    assert left_graph.plan().fingerprint == right_graph.plan().fingerprint


def test_explicit_load_policy_overrides_kind_default(tmp_path: Path) -> None:
    block = """
[[content.build.nodes]]
name = "title"
kind = "scene"
path = "scenes/title.swirscene"
load = "preload"
"""
    root, manifest = _project(tmp_path, block)
    (root / "scenes" / "title.swirscene").write_text("{}", encoding="utf-8")
    graph = ContentBuildGraph.load_optional(manifest)
    assert graph is not None
    assert graph.plan().preload_paths == ("scenes/title.swirscene",)
    assert graph.plan().stream_paths == ()


def test_graph_rejects_unknown_dependencies_and_cycles(tmp_path: Path) -> None:
    unknown = """
[[content.build.nodes]]
name = "asset:a"
path = "assets/a.bin"
depends_on = ["asset:missing"]
"""
    _, manifest = _project(tmp_path / "unknown", unknown)
    with pytest.raises(ContentBuildError, match="unknown node"):
        ContentBuildGraph.load_optional(manifest)

    cycle = """
[[content.build.nodes]]
name = "asset:a"
path = "assets/a.bin"
depends_on = ["asset:b"]
[[content.build.nodes]]
name = "asset:b"
path = "assets/b.bin"
depends_on = ["asset:a"]
"""
    _, manifest = _project(tmp_path / "cycle", cycle)
    with pytest.raises(ContentBuildError, match="dependency cycle"):
        ContentBuildGraph.load_optional(manifest)


def test_graph_rejects_duplicate_names_paths_and_dependency_entries(tmp_path: Path) -> None:
    duplicate_name = """
[[content.build.nodes]]
name = "same"
path = "assets/a.bin"
[[content.build.nodes]]
name = "same"
path = "assets/b.bin"
"""
    _, manifest = _project(tmp_path / "names", duplicate_name)
    with pytest.raises(ContentBuildError, match="declared more than once"):
        ContentBuildGraph.load_optional(manifest)

    duplicate_path = """
[[content.build.nodes]]
name = "a"
path = "assets/shared.bin"
[[content.build.nodes]]
name = "b"
path = "assets/shared.bin"
"""
    _, manifest = _project(tmp_path / "paths", duplicate_path)
    with pytest.raises(ContentBuildError, match="declared by both"):
        ContentBuildGraph.load_optional(manifest)

    duplicate_dependency = """
[[content.build.nodes]]
name = "a"
path = "assets/a.bin"
[[content.build.nodes]]
name = "b"
path = "assets/b.bin"
depends_on = ["a", "a"]
"""
    _, manifest = _project(tmp_path / "deps", duplicate_dependency)
    with pytest.raises(ContentBuildError, match="duplicate values"):
        ContentBuildGraph.load_optional(manifest)


@pytest.mark.parametrize(
    "unsafe",
    ["../outside.bin", "/tmp/outside.bin", r"C:\outside.bin"],
)
def test_graph_rejects_manifest_paths_outside_project(tmp_path: Path, unsafe: str) -> None:
    escaped = unsafe.replace("\\", "\\\\")
    block = f"""
[[content.build.nodes]]
name = "unsafe"
path = "{escaped}"
"""
    _, manifest = _project(tmp_path, block)
    with pytest.raises(ContentBuildError, match="inside the project|drive prefix"):
        ContentBuildGraph.load_optional(manifest)


def test_diagnostics_and_shipping_preflight_report_missing_content(tmp_path: Path) -> None:
    _, manifest = _project(tmp_path, BUILD)
    graph = ContentBuildGraph.load_optional(manifest)
    assert graph is not None

    diagnostics = graph.diagnostics()

    assert len(diagnostics) == 4
    assert {item.code for item in diagnostics} == {"content-build-missing"}
    with pytest.raises(ContentBuildError, match="content build preflight failed"):
        graph.shipping_paths()


def test_shipping_paths_are_dependency_ordered_and_require_real_files(tmp_path: Path) -> None:
    root, manifest = _project(tmp_path, BUILD)
    _write_content(root)
    graph = ContentBuildGraph.load_optional(manifest)
    assert graph is not None

    assert graph.shipping_paths() == (
        "shaders/world.glsl",
        "assets/world.bin",
        "generated/nav.bin",
        "scenes/level.swirscene",
    )


def test_plan_target_closure_does_not_pull_unrelated_nodes(tmp_path: Path) -> None:
    block = BUILD + """
[[content.build.nodes]]
name = "asset:credits"
kind = "asset"
path = "assets/credits.bin"
"""
    root, manifest = _project(tmp_path, block)
    _write_content(root)
    (root / "assets" / "credits.bin").write_bytes(b"credits")
    graph = ContentBuildGraph.load_optional(manifest)
    assert graph is not None

    plan = graph.plan(["scene:level"])

    assert "asset:credits" not in plan.ordered_nodes
    assert "assets/credits.bin" not in plan.all_paths


def test_plan_rejects_empty_duplicate_and_unknown_targets(tmp_path: Path) -> None:
    root, manifest = _project(tmp_path, BUILD)
    _write_content(root)
    graph = ContentBuildGraph.load_optional(manifest)
    assert graph is not None

    with pytest.raises(ContentBuildError, match="at least one target"):
        graph.plan([])
    with pytest.raises(ContentBuildError, match="must be unique"):
        graph.plan(["asset:world", "asset:world"])
    with pytest.raises(ContentBuildError, match="available nodes"):
        graph.plan(["missing"])


def test_runtime_plan_bridges_existing_preloader_and_streaming_manager(tmp_path: Path) -> None:
    block = """
[[content.build.nodes]]
name = "asset:boot"
kind = "asset"
path = "assets/boot.bin"
load = "preload"
[[content.build.nodes]]
name = "asset:late"
kind = "asset"
path = "assets/late.bin"
load = "stream"
depends_on = ["asset:boot"]
"""
    root, manifest = _project(tmp_path, block)
    (root / "assets" / "boot.bin").write_bytes(b"boot")
    (root / "assets" / "late.bin").write_bytes(b"late")
    graph = ContentBuildGraph.load_optional(manifest)
    assert graph is not None
    plan = graph.plan()

    assets = AssetManager(root)
    assets.register_loader(".bin", lambda path: path.read_bytes())
    with AssetPreloader(assets, max_workers=2) as preloader:
        report = plan.preload_with(preloader)
        assert report.total == 1
        assert report.failed == 0
        assert report.results[0].value == b"boot"

    with AssetStreamingManager(assets) as streaming:
        futures = plan.stage_streaming_with(streaming)
        assert len(futures) == 1
        assert futures[0].result(timeout=5).value == b"late"
        finalized = streaming.pump(max_completions=1)
        assert len(finalized) == 1
        assert streaming.diagnostics().resident_assets == 1


def test_symlink_escape_is_reported_by_filesystem_preflight(tmp_path: Path) -> None:
    root, manifest = _project(tmp_path / "project", """
[[content.build.nodes]]
name = "escape"
path = "assets/link.bin"
""")
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside")
    link = root / "assets" / "link.bin"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this runner")
    graph = ContentBuildGraph.load_optional(manifest)
    assert graph is not None

    diagnostics = graph.diagnostics()
    assert diagnostics[0].code == "content-build-path-escape"
    with pytest.raises(ContentBuildError, match="preflight failed"):
        graph.shipping_paths()


def test_invalid_kind_policy_and_empty_build_have_actionable_errors(tmp_path: Path) -> None:
    invalid_kind = """
[[content.build.nodes]]
name = "bad"
kind = "movie"
path = "assets/bad.bin"
"""
    _, manifest = _project(tmp_path / "kind", invalid_kind)
    with pytest.raises(ContentBuildError, match="must be one of"):
        ContentBuildGraph.load_optional(manifest)

    invalid_load = """
[[content.build.nodes]]
name = "bad"
path = "assets/bad.bin"
load = "instant"
"""
    _, manifest = _project(tmp_path / "load", invalid_load)
    with pytest.raises(ContentBuildError, match="must be one of"):
        ContentBuildGraph.load_optional(manifest)

    root, _ = _project(tmp_path / "empty", None)
    (root / "swirproject.toml").write_text(
        'name = "Empty"\n[content]\ninclude = ["assets"]\n[content.build]\nnodes = []\n',
        encoding="utf-8",
    )
    with pytest.raises(ContentBuildError, match="at least one"):
        ContentBuildGraph.load_optional(ProjectManifest.load(root))
