from __future__ import annotations

import io
import stat
import tarfile
import zipfile
from pathlib import Path

import pytest

from tools.verify_packaging_shipping_2_0 import (
    EXPECTED_VERSION,
    PackagingShippingError,
    _clean_env,
    _inspect_sdist,
    _inspect_wheel,
    _select_artifacts,
    _validate_member_names,
    _validate_member_sizes,
)


def test_select_artifacts_requires_one_wheel_and_one_sdist(tmp_path):
    wheel = tmp_path / f"swirengine-{EXPECTED_VERSION}-py3-none-any.whl"
    sdist = tmp_path / f"swirengine-{EXPECTED_VERSION}.tar.gz"
    wheel.write_bytes(b"wheel")
    sdist.write_bytes(b"sdist")

    artifacts = _select_artifacts(tmp_path)

    assert artifacts.wheel == wheel
    assert artifacts.sdist == sdist
    assert len(artifacts.wheel_sha256) == 64
    assert len(artifacts.sdist_sha256) == 64


def test_select_artifacts_rejects_ambiguous_distribution_set(tmp_path):
    (tmp_path / f"swirengine-{EXPECTED_VERSION}-py3-none-any.whl").write_bytes(b"a")
    (tmp_path / f"swirengine-{EXPECTED_VERSION}-extra-py3-none-any.whl").write_bytes(b"b")
    (tmp_path / f"swirengine-{EXPECTED_VERSION}.tar.gz").write_bytes(b"c")

    with pytest.raises(PackagingShippingError, match="exactly one"):
        _select_artifacts(tmp_path)


@pytest.mark.parametrize(
    "members",
    [
        ("swirengine-1.5.0/../escape.py",),
        ("/absolute/path.py",),
        ("C:/absolute/path.py",),
        (r"D:\\absolute\\path.py",),
        ("swirengine-1.5.0/.git/config",),
        ("swirengine-1.5.0/pkg.py", "SWIRENGINE-1.5.0/PKG.py"),
    ],
)
def test_archive_member_validation_rejects_unsafe_or_ambiguous_paths(members):
    with pytest.raises(PackagingShippingError):
        _validate_member_names(members, label="fixture")


def test_archive_size_validation_rejects_oversized_member_or_total():
    with pytest.raises(PackagingShippingError, match="oversized member"):
        _validate_member_sizes([64 * 1024 * 1024 + 1], label="fixture")

    with pytest.raises(PackagingShippingError, match="uncompressed size"):
        _validate_member_sizes([32 * 1024 * 1024] * 9, label="fixture")


def test_clean_env_strips_source_path_overrides():
    env = _clean_env({"PYTHONPATH": "repo", "PYTHONHOME": "python", "PATH": "bin"})

    assert "PYTHONPATH" not in env
    assert "PYTHONHOME" not in env
    assert env["PYTHONNOUSERSITE"] == "1"
    assert env["PYTHONDONTWRITEBYTECODE"] == "1"
    assert env["PATH"] == "bin"


def test_inspect_wheel_requires_expected_metadata_and_package(tmp_path):
    wheel = tmp_path / f"swirengine-{EXPECTED_VERSION}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            f"swirengine-{EXPECTED_VERSION}.dist-info/METADATA",
            f"Metadata-Version: 2.4\nName: swirengine\nVersion: {EXPECTED_VERSION}\n",
        )
        archive.writestr(
            "swirengine/__init__.py", f"__version__ = '{EXPECTED_VERSION}'\n"
        )

    _inspect_wheel(wheel)


def test_inspect_wheel_rejects_symlink_members(tmp_path):
    wheel = tmp_path / f"swirengine-{EXPECTED_VERSION}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            f"swirengine-{EXPECTED_VERSION}.dist-info/METADATA",
            f"Metadata-Version: 2.4\nName: swirengine\nVersion: {EXPECTED_VERSION}\n",
        )
        archive.writestr(
            "swirengine/__init__.py", f"__version__ = '{EXPECTED_VERSION}'\n"
        )
        link = zipfile.ZipInfo("swirengine/link")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, "../outside")

    with pytest.raises(PackagingShippingError, match="symlink"):
        _inspect_wheel(wheel)


def test_inspect_sdist_rejects_link_members(tmp_path):
    sdist = tmp_path / f"swirengine-{EXPECTED_VERSION}.tar.gz"
    with tarfile.open(sdist, "w:gz") as archive:
        metadata = (
            f"Metadata-Version: 2.4\nName: swirengine\nVersion: {EXPECTED_VERSION}\n".encode()
        )
        info = tarfile.TarInfo(f"swirengine-{EXPECTED_VERSION}/PKG-INFO")
        info.size = len(metadata)
        archive.addfile(info, io.BytesIO(metadata))

        package = f"__version__ = '{EXPECTED_VERSION}'\n".encode()
        info = tarfile.TarInfo(
            f"swirengine-{EXPECTED_VERSION}/src/swirengine/__init__.py"
        )
        info.size = len(package)
        archive.addfile(info, io.BytesIO(package))

        link = tarfile.TarInfo(f"swirengine-{EXPECTED_VERSION}/link")
        link.type = tarfile.SYMTYPE
        link.linkname = "../../outside"
        archive.addfile(link)

    with pytest.raises(PackagingShippingError, match="link/device"):
        _inspect_sdist(sdist)


def test_inspect_sdist_accepts_safe_expected_layout(tmp_path):
    sdist = tmp_path / f"swirengine-{EXPECTED_VERSION}.tar.gz"
    with tarfile.open(sdist, "w:gz") as archive:
        entries = {
            f"swirengine-{EXPECTED_VERSION}/PKG-INFO": (
                f"Metadata-Version: 2.4\nName: swirengine\nVersion: {EXPECTED_VERSION}\n".encode()
            ),
            f"swirengine-{EXPECTED_VERSION}/src/swirengine/__init__.py": (
                f"__version__ = '{EXPECTED_VERSION}'\n".encode()
            ),
        }
        for name, payload in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))

    _inspect_sdist(sdist)


def test_milestone_7_closeout_is_tied_to_verified_implementation_head():
    roadmap = Path("ROADMAP_2_0.md").read_text(encoding="utf-8")

    assert "- [x] **7. Packaging, Clean Install & Native Desktop Shipping**" in roadmap
    assert "`03aaef751260fc9de0c1a031f1f93b29fdd2c10c` passed every triggered" in roadmap
    assert "Milestone 7 is therefore verified at **7/10 = 70.0%**." in roadmap
