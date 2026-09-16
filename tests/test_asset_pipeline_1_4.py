from __future__ import annotations

from pathlib import Path
from threading import Event, get_ident

import pytest

from swirengine.asset_pipeline import (
    AssetDependencyGraph,
    AssetFingerprint,
    AssetImportState,
    AssetPipeline,
)
from swirengine.assets import AssetManager


def test_asset_fingerprint_detects_same_size_content_change(tmp_path: Path) -> None:
    path = tmp_path / "asset.bin"
    path.write_bytes(b"alpha")
    first = AssetFingerprint.capture(path)

    path.write_bytes(b"omega")
    second = AssetFingerprint.capture(path)

    assert first.exists and second.exists
    assert first.size_bytes == second.size_bytes == 5
    assert first.sha256 != second.sha256
    assert AssetFingerprint.capture(tmp_path / "missing.bin").exists is False


def test_dependency_graph_reports_transitive_dependents_cycle_safely(tmp_path: Path) -> None:
    graph = AssetDependencyGraph()
    texture = tmp_path / "texture.png"
    material = tmp_path / "material.json"
    model = tmp_path / "model.gltf"

    graph.set_dependencies(material, [texture])
    graph.set_dependencies(model, [material])
    assert graph.dependencies(model) == (material.resolve(),)
    assert graph.direct_dependents(texture) == (material.resolve(),)
    assert graph.affected_by(texture) == (
        material.resolve(),
        model.resolve(),
        texture.resolve(),
    )

    graph.set_dependencies(texture, [model])
    assert set(graph.affected_by(texture)) == {
        texture.resolve(),
        material.resolve(),
        model.resolve(),
    }


def test_background_loader_finalizes_on_caller_thread(tmp_path: Path) -> None:
    source = tmp_path / "scene.asset"
    source.write_text("raw", encoding="utf-8")
    manager = AssetManager(tmp_path)
    main_thread = get_ident()
    loader_threads: list[int] = []
    finalizer_threads: list[int] = []

    def loader(path: Path) -> str:
        loader_threads.append(get_ident())
        return path.read_text(encoding="utf-8")

    def finalizer(value: str) -> str:
        finalizer_threads.append(get_ident())
        return value.upper()

    with AssetPipeline(manager, max_workers=1) as pipeline:
        pipeline.register_processor(
            "scene",
            suffixes=["asset"],
            loader=loader,
            finalizer=finalizer,
        )
        result = pipeline.wait(pipeline.submit("scene.asset"), timeout=2)

    assert result.successful
    assert result.value == "RAW"
    assert loader_threads and loader_threads[0] != main_thread
    assert finalizer_threads == [main_thread]


def test_reentrant_finalizer_can_read_pipeline_diagnostics(tmp_path: Path) -> None:
    source = tmp_path / "scene.asset"
    source.write_text("raw", encoding="utf-8")
    manager = AssetManager(tmp_path)

    with AssetPipeline(manager, max_workers=1) as pipeline:

        def finalizer(value: str) -> tuple[str, int]:
            return value.upper(), pipeline.diagnostics.max_workers

        pipeline.register_processor(
            "scene",
            suffixes=["asset"],
            loader=lambda path: path.read_text(encoding="utf-8"),
            finalizer=finalizer,
        )
        result = pipeline.wait(pipeline.submit(source), timeout=2)

    assert result.successful
    assert result.value == ("RAW", 1)


def test_asset_pipeline_reuses_content_aware_cache(tmp_path: Path) -> None:
    source = tmp_path / "config.txt"
    source.write_text("alpha", encoding="utf-8")
    manager = AssetManager(tmp_path)
    calls = 0

    def loader(path: Path) -> str:
        nonlocal calls
        calls += 1
        return path.read_text(encoding="utf-8")

    with AssetPipeline(manager, max_workers=1) as pipeline:
        pipeline.register_processor("text", suffixes=["txt"], loader=loader)
        first = pipeline.wait(pipeline.submit("config.txt"), timeout=2)
        second = pipeline.wait(pipeline.submit("config.txt"), timeout=2)
        diagnostics = pipeline.diagnostics

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second.value == "alpha"
    assert calls == 1
    assert diagnostics.cache_hits == 1
    assert diagnostics.cache_misses == 1
    assert diagnostics.cached_entries == 1


def test_dependency_fingerprint_invalidates_derived_cache(tmp_path: Path) -> None:
    source = tmp_path / "model.asset"
    dependency = tmp_path / "texture.bin"
    source.write_text("model", encoding="utf-8")
    dependency.write_bytes(b"first")
    manager = AssetManager(tmp_path)
    calls = 0

    def loader(path: Path) -> tuple[str, bytes]:
        nonlocal calls
        calls += 1
        return path.read_text(encoding="utf-8"), dependency.read_bytes()

    with AssetPipeline(manager, max_workers=1) as pipeline:
        pipeline.register_processor(
            "model",
            suffixes=["asset"],
            loader=loader,
            dependencies=lambda _path: [dependency],
        )
        first = pipeline.wait(pipeline.submit(source), timeout=2)
        assert first.dependencies == (dependency.resolve(),)
        assert pipeline.cached(source)

        dependency.write_bytes(b"second")
        assert pipeline.cached(source) is False
        second = pipeline.wait(pipeline.submit(source), timeout=2)

    assert first.cache_hit is False
    assert second.cache_hit is False
    assert second.value == ("model", b"second")
    assert calls == 2


def test_asset_manager_invalidation_propagates_to_dependents(tmp_path: Path) -> None:
    source = tmp_path / "material.asset"
    dependency = tmp_path / "albedo.png"
    source.write_text("material", encoding="utf-8")
    dependency.write_bytes(b"png")
    manager = AssetManager(tmp_path)

    with AssetPipeline(manager, max_workers=1) as pipeline:
        pipeline.register_processor(
            "material",
            suffixes=["asset"],
            loader=lambda path: path.read_text(encoding="utf-8"),
            dependencies=lambda _path: [dependency],
        )
        pipeline.wait(pipeline.submit(source), timeout=2)
        assert pipeline.diagnostics.cached_entries == 1

        manager.invalidate(dependency)
        diagnostics = pipeline.diagnostics

    assert diagnostics.cached_entries == 0
    assert diagnostics.invalidated_entries == 1


def test_import_is_stale_when_source_changes_during_worker(tmp_path: Path) -> None:
    source = tmp_path / "slow.asset"
    source.write_text("before", encoding="utf-8")
    manager = AssetManager(tmp_path)
    started = Event()
    release = Event()
    finalized: list[str] = []

    def loader(path: Path) -> str:
        value = path.read_text(encoding="utf-8")
        started.set()
        assert release.wait(timeout=2)
        return value

    with AssetPipeline(manager, max_workers=1) as pipeline:
        pipeline.register_processor(
            "slow",
            suffixes=["asset"],
            loader=loader,
            finalizer=lambda value: finalized.append(value) or value,
        )
        request = pipeline.submit(source)
        assert started.wait(timeout=2)
        source.write_text("after-change", encoding="utf-8")
        release.set()
        result = pipeline.wait(request, timeout=2)
        diagnostics = pipeline.diagnostics

    assert result.state is AssetImportState.STALE
    assert result.successful is False
    assert finalized == []
    assert diagnostics.stale == 1
    assert diagnostics.cached_entries == 0


def test_import_is_stale_when_dependency_changes_during_worker(tmp_path: Path) -> None:
    source = tmp_path / "slow.asset"
    dependency = tmp_path / "texture.bin"
    source.write_text("model", encoding="utf-8")
    dependency.write_bytes(b"before")
    manager = AssetManager(tmp_path)
    started = Event()
    release = Event()

    def loader(path: Path) -> tuple[str, bytes]:
        source_value = path.read_text(encoding="utf-8")
        dependency_value = dependency.read_bytes()
        started.set()
        assert release.wait(timeout=2)
        return source_value, dependency_value

    with AssetPipeline(manager, max_workers=1) as pipeline:
        pipeline.register_processor(
            "slow",
            suffixes=["asset"],
            loader=loader,
            dependencies=lambda _path: [dependency],
        )
        request = pipeline.submit(source)
        assert started.wait(timeout=2)
        dependency.write_bytes(b"after-change")
        release.set()
        result = pipeline.wait(request, timeout=2)

    assert result.state is AssetImportState.STALE
    assert result.successful is False
    assert result.dependencies == (dependency.resolve(),)


def test_failed_processor_does_not_poison_cache(tmp_path: Path) -> None:
    source = tmp_path / "broken.asset"
    source.write_text("broken", encoding="utf-8")
    manager = AssetManager(tmp_path)

    with AssetPipeline(manager, max_workers=1) as pipeline:
        pipeline.register_processor(
            "broken",
            suffixes=["asset"],
            loader=lambda _path: (_ for _ in ()).throw(ValueError("bad import")),
        )
        result = pipeline.wait(pipeline.submit(source), timeout=2)

    assert result.state is AssetImportState.FAILED
    assert result.error == "bad import"


def test_processor_registration_rejects_suffix_conflicts(tmp_path: Path) -> None:
    pipeline = AssetPipeline(AssetManager(tmp_path), max_workers=1)
    pipeline.register_processor("first", suffixes=["txt"], loader=Path.read_text)
    with pytest.raises(ValueError, match="already owned"):
        pipeline.register_processor("second", suffixes=[".txt"], loader=Path.read_text)
    pipeline.close()


def test_asset_pipeline_rejects_invalid_workers(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="max_workers"):
        AssetPipeline(AssetManager(tmp_path), max_workers=0)
