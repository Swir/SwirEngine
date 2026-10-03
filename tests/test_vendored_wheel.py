from __future__ import annotations

import csv
import io
import zipfile

import pytest

from tools.build_vendored_wheel import build_vendored_wheel


def _write_wheel(path, files: dict[str, bytes]) -> None:
    _write_wheel_entries(path, list(files.items()))


def _write_wheel_entries(path, entries: list[tuple[str, bytes]]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries:
            info = zipfile.ZipInfo("placeholder")
            info.filename = name
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)


def _base_wheel(tmp_path):
    path = tmp_path / "swirengine-1.0.3-py3-none-any.whl"
    _write_wheel(
        path,
        {
            "swirengine/__init__.py": b'__version__ = "1.0.3"\n',
            "swirengine-1.0.3.dist-info/METADATA": b"Name: swirengine\nVersion: 1.0.3\n",
            "swirengine-1.0.3.dist-info/WHEEL": (
                b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
            ),
            "swirengine-1.0.3.dist-info/RECORD": b"",
        },
    )
    return path


def _vendor_wheel(tmp_path, name: str, entries: list[tuple[str, bytes]]):
    path = tmp_path / name
    _write_wheel_entries(
        path,
        entries
        + [
            ("vendor-1.0.0.dist-info/METADATA", b"Name: vendor\nVersion: 1.0.0\n"),
            ("vendor-1.0.0.dist-info/RECORD", b""),
        ],
    )
    return path


def test_build_vendored_wheel_creates_platform_specific_archive(tmp_path):
    base = tmp_path / "swirengine-1.0.3-py3-none-any.whl"
    _write_wheel(
        base,
        {
            "swirengine/__init__.py": b'__version__ = "1.0.3"\n',
            "swirengine-1.0.3.dist-info/METADATA": b"Name: swirengine\nVersion: 1.0.3\n",
            "swirengine-1.0.3.dist-info/WHEEL": (
                b"Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
            ),
            "swirengine-1.0.3.dist-info/RECORD": b"",
        },
    )
    moderngl = tmp_path / "moderngl-5.12.0-cp314-cp314-win_amd64.whl"
    _write_wheel(
        moderngl,
        {
            "_moderngl.py": b"VALUE = 1\n",
            "moderngl/__init__.py": b"VALUE = 2\n",
            "moderngl/mgl.cp314-win_amd64.pyd": b"native-moderngl",
            "moderngl-5.12.0.dist-info/licenses/LICENSE": b"ModernGL license",
            "moderngl-5.12.0.dist-info/RECORD": b"",
        },
    )
    glcontext = tmp_path / "glcontext-3.0.0-cp314-cp314-win_amd64.whl"
    _write_wheel(
        glcontext,
        {
            "glcontext/__init__.py": b"VALUE = 3\n",
            "glcontext/wgl.cp314-win_amd64.pyd": b"native-glcontext",
            "glcontext-3.0.0.dist-info/licenses/LICENSE": b"glcontext license",
            "glcontext-3.0.0.dist-info/RECORD": b"",
        },
    )

    output = build_vendored_wheel(
        base,
        [moderngl, glcontext],
        tag="cp314-cp314-win_amd64",
        output_dir=tmp_path / "dist",
    )

    assert output.name == "swirengine-1.0.3-cp314-cp314-win_amd64.whl"
    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
        assert "swirengine/_vendor_native/moderngl/__init__.py" in names
        assert "swirengine/_vendor_native/moderngl/mgl.cp314-win_amd64.pyd" in names
        assert "swirengine/_vendor_native/glcontext/wgl.cp314-win_amd64.pyd" in names
        assert "swirengine/_vendor_native/_moderngl.py" in names
        assert archive.read("swirengine_native_vendor.pth") == b"swirengine/_vendor_native\n"

        wheel_metadata = archive.read("swirengine-1.0.3.dist-info/WHEEL").decode()
        assert "Root-Is-Purelib: false" in wheel_metadata
        assert "Tag: cp314-cp314-win_amd64" in wheel_metadata
        assert "Tag: py3-none-any" not in wheel_metadata

        assert (
            archive.read("swirengine-1.0.3.dist-info/licenses/vendor/moderngl/LICENSE")
            == b"ModernGL license"
        )
        assert (
            archive.read("swirengine-1.0.3.dist-info/licenses/vendor/glcontext/LICENSE")
            == b"glcontext license"
        )

        record_text = archive.read("swirengine-1.0.3.dist-info/RECORD").decode()
        rows = list(csv.reader(io.StringIO(record_text)))
        recorded = {row[0] for row in rows}
        assert recorded == names
        record_row = next(row for row in rows if row[0].endswith("/RECORD"))
        assert record_row[1:] == ["", ""]


@pytest.mark.parametrize(
    "unsafe_name",
    [
        "../../sitecustomize.py",
        "/absolute.py",
        r"bad\path.py",
        "pkg//payload.py",
        "pkg/./payload.py",
        "pkg/path./payload.py",
        "pkg/COM¹/payload.py",
        "pkg/CONOUT$.txt",
        "pkg/bad?.py",
        "pkg/control\x01.py",
    ],
)
def test_build_vendored_wheel_rejects_unsafe_vendor_members(
    tmp_path, unsafe_name: str
) -> None:
    base = _base_wheel(tmp_path)
    vendor = _vendor_wheel(
        tmp_path,
        "vendor-1.0.0-py3-none-any.whl",
        [(unsafe_name, b"payload")],
    )

    with pytest.raises(ValueError, match="wheel member path|device wheel member"):
        build_vendored_wheel(
            base,
            [vendor],
            tag="cp314-cp314-win_amd64",
            output_dir=tmp_path / "dist",
        )


def test_build_vendored_wheel_rejects_casefold_member_collision(tmp_path) -> None:
    base = _base_wheel(tmp_path)
    vendor = _vendor_wheel(
        tmp_path,
        "vendor-1.0.0-py3-none-any.whl",
        [("Package.py", b"one"), ("package.py", b"two")],
    )

    with pytest.raises(ValueError, match="duplicate/Windows-colliding wheel member"):
        build_vendored_wheel(
            base,
            [vendor],
            tag="cp314-cp314-win_amd64",
            output_dir=tmp_path / "dist",
        )


def test_build_vendored_wheel_rejects_cross_vendor_output_collision(tmp_path) -> None:
    base = _base_wheel(tmp_path)
    first = _vendor_wheel(
        tmp_path,
        "first-1.0.0-py3-none-any.whl",
        [("shared.py", b"one")],
    )
    second = _vendor_wheel(
        tmp_path,
        "second-1.0.0-py3-none-any.whl",
        [("Shared.py", b"two")],
    )

    with pytest.raises(ValueError, match="duplicate/Windows-colliding output member"):
        build_vendored_wheel(
            base,
            [first, second],
            tag="cp314-cp314-win_amd64",
            output_dir=tmp_path / "dist",
        )


def test_build_vendored_wheel_rejects_unsafe_platform_tag(tmp_path) -> None:
    base = _base_wheel(tmp_path)
    vendor = _vendor_wheel(
        tmp_path,
        "vendor-1.0.0-py3-none-any.whl",
        [("vendor/__init__.py", b"")],
    )

    with pytest.raises(ValueError, match="invalid platform wheel tag"):
        build_vendored_wheel(
            base,
            [vendor],
            tag="../../outside",
            output_dir=tmp_path / "dist",
        )
