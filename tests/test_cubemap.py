from pathlib import Path

import pytest
from PIL import Image

from swirengine.graphics.cubemap import (
    CubemapFaces,
    ImageBasedEnvironment3D,
    cubemap_asset_paths,
    load_cubemap_faces,
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
