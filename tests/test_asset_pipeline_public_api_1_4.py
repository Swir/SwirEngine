from swirengine import (
    AssetDependencyGraph,
    AssetFingerprint,
    AssetImportDiagnostics,
    AssetImportRequest,
    AssetImportResult,
    AssetImportState,
    AssetPipeline,
    DerivedAssetCache,
    DerivedAssetCacheDiagnostics,
    gltf_asset_dependencies,
    register_gltf_asset_processor,
)


def test_asset_pipeline_2_public_symbols_are_exported() -> None:
    assert AssetPipeline.__name__ == "AssetPipeline"
    assert AssetDependencyGraph.__name__ == "AssetDependencyGraph"
    assert AssetFingerprint.__name__ == "AssetFingerprint"
    assert AssetImportDiagnostics.__name__ == "AssetImportDiagnostics"
    assert AssetImportRequest.__name__ == "AssetImportRequest"
    assert AssetImportResult.__name__ == "AssetImportResult"
    assert AssetImportState.COMPLETED.value == "completed"
    assert DerivedAssetCache.__name__ == "DerivedAssetCache"
    assert DerivedAssetCacheDiagnostics.__name__ == "DerivedAssetCacheDiagnostics"
    assert callable(gltf_asset_dependencies)
    assert callable(register_gltf_asset_processor)
