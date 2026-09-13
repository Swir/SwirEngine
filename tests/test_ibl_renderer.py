from pathlib import Path

from swirengine.graphics.cubemap import CubemapFaces, ImageBasedEnvironment3D
from swirengine.graphics.ibl_renderer import ImageBasedPostProcessRenderer
from swirengine.graphics.stats import RendererStats


class FakeCubemap:
    def __init__(self) -> None:
        self.released = False
        self.used_locations: list[int] = []
        self.texture = type("Texture", (), {"filter": None})()

    def use(self, location: int = 0) -> None:
        self.used_locations.append(location)

    def release(self) -> None:
        self.released = True


class FakeEnvironment:
    def __init__(self, paths: tuple[Path, ...]) -> None:
        self.cubemap = type("Faces", (), {"paths": lambda _self: paths})()
        self.uploads = 0
        self.resource = FakeCubemap()

    def upload(self, _ctx, *, build_mipmaps: bool = True):
        assert build_mipmaps is True
        self.uploads += 1
        return self.resource


def _faces(root: Path, prefix: str = "face") -> CubemapFaces:
    paths = tuple(root / f"{prefix}-{index}.png" for index in range(6))
    return CubemapFaces(*paths)


def test_environment_selection_uses_first_enabled_environment(tmp_path):
    disabled = ImageBasedEnvironment3D(_faces(tmp_path, "disabled"), enabled=False)
    enabled = ImageBasedEnvironment3D(_faces(tmp_path, "enabled"))
    scene = type("Scene", (), {"objects": [disabled, enabled]})()

    assert ImageBasedPostProcessRenderer._environment(scene) is enabled


def test_cubemap_cache_reuses_uploaded_environment(tmp_path):
    renderer = ImageBasedPostProcessRenderer.__new__(ImageBasedPostProcessRenderer)
    renderer.ctx = type("Context", (), {"LINEAR_MIPMAP_LINEAR": 1, "LINEAR": 2})()
    renderer.stats = RendererStats()
    renderer._ibl_cubemaps = {}
    paths = tuple(tmp_path / f"face-{index}.png" for index in range(6))
    environment = FakeEnvironment(paths)

    first = renderer._cubemap(environment)
    second = renderer._cubemap(environment)

    assert first is second
    assert environment.uploads == 1
    assert first.texture.filter == (1, 2)
    assert renderer.stats.texture_uploads == 1


def test_invalidate_cubemap_releases_only_matching_environment(tmp_path):
    renderer = ImageBasedPostProcessRenderer.__new__(ImageBasedPostProcessRenderer)
    first = FakeCubemap()
    second = FakeCubemap()
    target = str((tmp_path / "target.png").resolve())
    renderer._ibl_cubemaps = {
        (target, "a", "b", "c", "d", "e"): first,
        (str((tmp_path / "other.png").resolve()), "1", "2", "3", "4", "5"): second,
    }

    assert renderer.invalidate_cubemap(target) is True
    assert first.released is True
    assert second.released is False
    assert len(renderer._ibl_cubemaps) == 1
    assert renderer.invalidate_cubemap(tmp_path / "missing.png") is False
