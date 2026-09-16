from pathlib import Path

from swirengine.asset_pipeline import AssetPipeline
from swirengine.assets import AssetManager


def test_watched_dependency_change_invalidates_derived_asset_cache(tmp_path: Path) -> None:
    source = tmp_path / "material.asset"
    dependency = tmp_path / "albedo.texture"
    source.write_text("material", encoding="utf-8")
    dependency.write_text("v1", encoding="utf-8")
    manager = AssetManager(tmp_path)
    manager.watch(dependency)

    with AssetPipeline(manager, max_workers=1) as pipeline:
        pipeline.register_processor(
            "material",
            suffixes=(".asset",),
            loader=lambda path: path.read_text(encoding="utf-8"),
            dependencies=lambda _path: (dependency,),
        )
        first = pipeline.wait(pipeline.submit(source), timeout=2)
        assert first.successful
        assert pipeline.diagnostics.cached_entries == 1

        dependency.write_text("v2-changed", encoding="utf-8")
        reloads = manager.poll_changes(reload_cached=False)

        assert len(reloads) == 1
        assert reloads[0].path == dependency.resolve()
        assert reloads[0].kind == "modified"
        assert pipeline.diagnostics.cached_entries == 0
        assert pipeline.diagnostics.invalidated_entries == 1

        refreshed = pipeline.wait(pipeline.submit(source), timeout=2)

    assert refreshed.successful
    assert refreshed.cache_hit is False
