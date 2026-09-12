from pathlib import Path

from swirengine import AssetManager, Material3D, Mesh3D, RendererAssetBridge, Scene, Sprite2D, cube_mesh


class FakeTexture:
    def __init__(self) -> None:
        self.released = False

    def release(self) -> None:
        self.released = True


class FakeRenderer:
    def __init__(self) -> None:
        self._textures: dict[str, tuple[FakeTexture, int, int]] = {}


def test_renderer_asset_bridge_releases_cached_gpu_texture(tmp_path):
    image = tmp_path / "hero.png"
    image.write_bytes(b"old")
    assets = AssetManager(tmp_path)
    renderer = FakeRenderer()
    texture = FakeTexture()
    renderer._textures[str(image.resolve())] = (texture, 64, 64)

    bridge = RendererAssetBridge(renderer, assets).bind()
    assert bridge.invalidate_texture(image) is True
    assert texture.released is True
    assert renderer._textures == {}
    assert bridge.invalidations[-1].released is True
    assert bridge.unbind() is True
    assert bridge.unbind() is False


def test_renderer_asset_bridge_watches_scene_2d_and_3d_textures(tmp_path):
    sprite_path = tmp_path / "sprite.png"
    albedo_path = tmp_path / "albedo.png"
    packed_path = tmp_path / "packed.png"
    for path in (sprite_path, albedo_path, packed_path):
        path.write_bytes(b"x")

    scene = Scene()
    scene.add(Sprite2D(sprite_path))
    scene.add(
        Mesh3D(
            cube_mesh(),
            material=Material3D(
                texture=albedo_path,
                metallic=0.5,
                roughness=0.5,
                metallic_roughness_texture=packed_path,
            ),
        )
    )

    assets = AssetManager(tmp_path)
    bridge = RendererAssetBridge(FakeRenderer(), assets)
    watched = bridge.watch_scene_textures(scene)

    assert watched == tuple(sorted((albedo_path, packed_path, sprite_path), key=lambda p: p.as_posix()))
    assert set(assets.watcher.paths) == {path.resolve() for path in watched}


def test_renderer_asset_bridge_poll_invalidates_gpu_cache_after_file_change(tmp_path):
    image = tmp_path / "hero.png"
    image.write_bytes(b"one")
    assets = AssetManager(tmp_path)
    renderer = FakeRenderer()
    texture = FakeTexture()
    renderer._textures[str(image.resolve())] = (texture, 16, 16)

    bridge = RendererAssetBridge(renderer, assets).bind()
    bridge.watch(image)
    image.write_bytes(b"two-two")

    results = bridge.poll()

    assert len(results) == 1
    assert results[0].kind == "modified"
    assert texture.released is True
    assert str(image.resolve()) not in renderer._textures
    assert bridge.invalidations[-1].path == image.resolve()


def test_renderer_asset_bridge_context_manager_unbinds(tmp_path):
    assets = AssetManager(tmp_path)
    renderer = FakeRenderer()
    with RendererAssetBridge(renderer, assets) as bridge:
        assert bridge.bound is True
    assert bridge.bound is False


def test_watch_scene_textures_rejects_non_iterable(tmp_path):
    bridge = RendererAssetBridge(FakeRenderer(), AssetManager(tmp_path))
    try:
        bridge.watch_scene_textures(object())
    except TypeError as exc:
        assert "scene_or_objects" in str(exc)
    else:
        raise AssertionError("TypeError was not raised")
