"""Self-contained SwirEngine 1.9 content build graph creator demo."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from swirengine.assets import AssetManager
from swirengine.asset_pipeline import AssetPreloader
from swirengine.asset_streaming import AssetStreamingManager
from swirengine.content_build19 import ContentBuildGraph
from swirengine.project19 import ProjectManifest


MANIFEST = """
name = "Content Build Demo"
mode = "3d"
entrypoint = "main.py"

[content]
include = ["assets"]

[[content.build.nodes]]
name = "shader:world"
kind = "shader"
path = "shaders/world.glsl"

[[content.build.nodes]]
name = "asset:boot"
kind = "asset"
path = "assets/boot.bin"
depends_on = ["shader:world"]

[[content.build.nodes]]
name = "scene:level"
kind = "scene"
path = "scenes/level.bin"
depends_on = ["asset:boot"]
"""


def _make_project(root: Path) -> None:
    for directory in ("assets", "shaders", "scenes"):
        (root / directory).mkdir(parents=True, exist_ok=True)
    (root / "main.py").write_text("print('demo')\n", encoding="utf-8")
    (root / "shaders" / "world.glsl").write_text("void main() {}\n", encoding="utf-8")
    (root / "assets" / "boot.bin").write_bytes(b"boot")
    (root / "scenes" / "level.bin").write_bytes(b"level")
    (root / "swirproject.toml").write_text(MANIFEST.strip() + "\n", encoding="utf-8")


def main() -> int:
    with TemporaryDirectory(prefix="swir-content-build-demo-") as directory:
        root = Path(directory)
        _make_project(root)
        project = ProjectManifest.load(root)
        graph = ContentBuildGraph.load_optional(project)
        if graph is None:
            raise RuntimeError("demo manifest did not activate [content.build]")
        if graph.diagnostics():
            raise RuntimeError(f"unexpected content diagnostics: {graph.diagnostics()!r}")

        plan = graph.plan(["scene:level"])
        print("content fingerprint:", graph.fingerprint)
        print("dependency order:", " -> ".join(plan.ordered_nodes))
        print("shader warmup inputs:", plan.warmup_paths)
        print("startup preload inputs:", plan.preload_paths)
        print("stream-on-demand inputs:", plan.stream_paths)

        # Real games register format-specific loaders. A bytes loader keeps the demo deterministic.
        assets = AssetManager(project.root)
        assets.register_loader(".bin", lambda path: path.read_bytes())

        with AssetPreloader(assets, max_workers=2) as preloader:
            report = plan.preload_with(preloader)
            if report.failed:
                raise RuntimeError(f"preload failed: {report.errors()!r}")
            print(f"preload: {report.loaded}/{report.total} loaded")

        with AssetStreamingManager(assets) as streaming:
            futures = plan.stage_streaming_with(streaming)
            for future in futures:
                future.result(timeout=5)
            while streaming.diagnostics().pending:
                streaming.pump(max_completions=4)
            print("resident streamed assets:", streaming.diagnostics().resident_assets)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
