from pathlib import Path

import pytest
from PIL import Image

from swirengine.graphics.cubemap import (
    CubemapFaces,
    CubemapImageData,
    ImageBasedEnvironment3D,
    cubemap_asset_paths,
    load_cubemap_faces,
    upload_cubemap,
)


def _faces(tmp_path: Path, *, mismatched: bool = False) -> CubemapFaces:
    tmp_path.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for index, name in enumerate(("px", "nx", "py", "ny", "pz", "nz")):
        size = (4, 2) if mismatched and index == 5 else (4, 4)
        path = tmp_path / f"{name}.png"
        Image.new("RGBA", size, (index * 20, 40, 80, 128)).save(path)
        paths.append(path)
    return CubemapFaces(*paths)


class _FakeTextureCube:
    def __init__(self) -> None:
        self.writes: list[tuple[int, bytes, int]] = []
        self.mipmap_builds = 0
        self.used_locations: list[int] = []
        self.release_count = 0

    def write(self, face: int, data: bytes, *, alignment: int = 1) -> None:
        self.writes.append((face, data, alignment))

    def build_mipmaps(self) -> None:
        self.mipmap_builds += 1

    def use(self, *, location: int = 0) -> None:
        self.used_locations.append(location)

    def release(self) -> None:
        self.release_count += 1


class _FakeContext:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[int, int], int, int, str]] = []
        self.texture = _FakeTextureCube()

    def texture_cube(
        self,
        size: tuple[int, int],
        components: int,
        *,
        alignment: int,
        dtype: str,
    ) -> _FakeTextureCube:
        self.calls.append((size, components, alignment, dtype))
        return self.texture


def test_cubemap_loader_normalizes_rgb_and_preserves_face_order(tmp_path: Path) -> None:
    faces = _faces(tmp_path)

    data = load_cubemap_faces(faces)

    assert (data.width, data.height, data.components) == (4, 4, 3)
    assert len(data.faces) == 6
    assert data.face_size_bytes == 48
    assert data.total_size_bytes == 288
    assert data.faces[0][:3] == bytes((0, 40, 80))
    assert data.faces[5][:3] == bytes((100, 40, 80))


def test_cubemap_loader_rejects_missing_and_mismatched_faces(tmp_path: Path) -> None:
    faces = _faces(tmp_path)
    Path(faces.negative_z).unlink()
    with pytest.raises(FileNotFoundError, match="negative_z"):
        load_cubemap_faces(faces)

    mismatched = _faces(tmp_path / "mismatch", mismatched=True)
    with pytest.raises(ValueError, match="identical dimensions"):
        load_cubemap_faces(mismatched)


def test_ibl_environment_validates_settings_and_keeps_required_tags(tmp_path: Path) -> None:
    faces = _faces(tmp_path)
    environment = ImageBasedEnvironment3D(
        faces,
        intensity=1.5,
        diffuse_strength=0.8,
        specular_strength=1.2,
        max_specular_lod=4.0,
        tags={"outdoor"},
    )

    assert environment.intensity == 1.5
    assert {"outdoor", "environment", "ibl"} <= environment.tags
    assert environment.load().total_size_bytes == 288

    with pytest.raises(ValueError, match="intensity"):
        ImageBasedEnvironment3D(faces, intensity=-0.1)
    with pytest.raises(ValueError, match="diffuse_strength"):
        ImageBasedEnvironment3D(faces, diffuse_strength=-1.0)
    with pytest.raises(ValueError, match="specular_strength"):
        ImageBasedEnvironment3D(faces, specular_strength=-1.0)


def test_cubemap_asset_paths_are_unique_deterministic_and_ignore_disabled(tmp_path: Path) -> None:
    faces = _faces(tmp_path)
    enabled = ImageBasedEnvironment3D(faces)
    duplicate = ImageBasedEnvironment3D(faces)
    disabled = ImageBasedEnvironment3D(faces, enabled=False)

    paths = cubemap_asset_paths((enabled, duplicate, disabled, object()))

    assert paths == tuple(path.resolve() for path in faces.paths())


def test_gpu_upload_writes_faces_in_opengl_order_and_builds_mipmaps(tmp_path: Path) -> None:
    data = load_cubemap_faces(_faces(tmp_path))
    ctx = _FakeContext()

    resource = upload_cubemap(ctx, data)

    assert ctx.calls == [((4, 4), 3, 1, "f1")]
    assert [face for face, _, _ in ctx.texture.writes] == list(range(6))
    assert [payload for _, payload, _ in ctx.texture.writes] == list(data.faces)
    assert all(alignment == 1 for _, _, alignment in ctx.texture.writes)
    assert ctx.texture.mipmap_builds == 1
    assert resource.mipmapped is True

    resource.use(5)
    assert ctx.texture.used_locations == [5]
    resource.release()
    resource.release()
    assert ctx.texture.release_count == 1
    with pytest.raises(RuntimeError, match="released"):
        resource.use()


def test_gpu_replace_requires_matching_shape_and_can_skip_mipmaps(tmp_path: Path) -> None:
    data = load_cubemap_faces(_faces(tmp_path))
    ctx = _FakeContext()
    resource = upload_cubemap(ctx, data, build_mipmaps=False)

    assert resource.mipmapped is False
    assert ctx.texture.mipmap_builds == 0

    resource.replace(data, build_mipmaps=True)
    assert ctx.texture.mipmap_builds == 1
    assert resource.mipmapped is True

    wrong = CubemapImageData(2, 2, 3, (bytes(12),) * 6)
    with pytest.raises(ValueError, match="must match"):
        resource.replace(wrong)


def test_gpu_upload_releases_texture_when_face_write_fails() -> None:
    class _BrokenTexture(_FakeTextureCube):
        def write(self, face: int, data: bytes, *, alignment: int = 1) -> None:
            super().write(face, data, alignment=alignment)
            if face == 2:
                raise RuntimeError("upload failed")

    class _BrokenContext(_FakeContext):
        def __init__(self) -> None:
            super().__init__()
            self.texture = _BrokenTexture()

    data = CubemapImageData(1, 1, 3, (bytes((1, 2, 3)),) * 6)
    ctx = _BrokenContext()

    with pytest.raises(RuntimeError, match="upload failed"):
        upload_cubemap(ctx, data)
    assert ctx.texture.release_count == 1
