"""SwirEngine 1.9 content build graph creator demo.

Run from a project that contains ``swirproject.toml`` with ``[[content.build.nodes]]`` entries.
The example intentionally keeps shader warmup creator-controlled while connecting preload and stream
batches to the established runtime systems.
"""

from __future__ import annotations

from pathlib import Path

from swirengine.asset_pipeline import AssetPreloader
from swirengine.asset_streaming import AssetStreamingManager
from swirengine.assets import AssetManager
from swirengine.content_build19 import ContentBuildGraph
from swirengine.project19 import ProjectManifest


project = ProjectManifest.load(Path.cwd())
graph = ContentBuildGraph.load_optional(project)
if graph is None:
    raise SystemExit("This project does not declare [content.build].")

errors = tuple(item for item in graph.diagnostics() if item.severity == "error")
if errors:
    for item in errors:
        print(f"ERROR {item.code}: {item.message} ({item.path or '-'})")
    raise SystemExit(2)

plan = graph.plan()
print("content fingerprint:", graph.fingerprint)
print("dependency order:", " -> ".join(plan.ordered_nodes))
print("shader/generated warmup inputs:", plan.warmup_paths)
print("startup preload inputs:", plan.preload_paths)
print("stream-on-demand inputs:", plan.stream_paths)

# AssetManager can use the project root when graph paths are project-relative. Real games normally
# register format-specific loaders during startup. This demo registers a bytes loader for clarity.
assets = AssetManager(project.root)
for suffix in {Path(path).suffix.lower() for path in (*plan.preload_paths, *plan.stream_paths)}:
    if suffix:
        assets.register_loader(suffix, lambda path: path.read_bytes())

with AssetPreloader(assets, max_workers=4) as preloader:
    preload_report = plan.preload_with(preloader)
    print(
        "preload:",
        f"{preload_report.loaded}/{preload_report.total} loaded,",
        f"{preload_report.wall_time_ms:.2f} ms",
    )

with AssetStreamingManager(assets) as streaming:
    plan.stage_streaming_with(streaming)
    while streaming.diagnostics().pending:
        streaming.pump(max_completions=4)
    print("resident streamed assets:", streaming.diagnostics().resident_assets)
