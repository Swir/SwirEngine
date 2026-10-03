from __future__ import annotations

import gzip
import io
import tarfile
from pathlib import Path

import pytest

from tools.verify_sdist_identity_2_2 import (
    SdistIdentityError,
    compare_sdists,
    inspect_sdist,
)


def _archive(
    path: Path,
    entries: list[tuple[str, str, bytes, int]],
    *,
    gzip_mtime: int = 0,
) -> None:
    with (
        path.open("wb") as raw,
        gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=gzip_mtime) as compressed,
        tarfile.open(fileobj=compressed, mode="w") as archive,
    ):
        for name, kind, content, mode in entries:
            info = tarfile.TarInfo(name)
            info.mode = mode
            info.mtime = 123
            if kind == "file":
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))
            elif kind == "directory":
                info.type = tarfile.DIRTYPE
                info.size = 0
                archive.addfile(info)
            elif kind == "symlink":
                info.type = tarfile.SYMTYPE
                info.linkname = "target"
                archive.addfile(info)
            elif kind == "hardlink":
                info.type = tarfile.LNKTYPE
                info.linkname = "root/target"
                archive.addfile(info)
            elif kind == "character-device":
                info.type = tarfile.CHRTYPE
                archive.addfile(info)
            else:  # pragma: no cover - test helper guard
                raise AssertionError(kind)


def _valid_entries(root: str = "swirengine-2.2.0") -> list[tuple[str, str, bytes, int]]:
    return [
        (root, "directory", b"", 0o755),
        (f"{root}/src", "directory", b"", 0o755),
        (f"{root}/src/swirengine", "directory", b"", 0o755),
        (f"{root}/src/swirengine/__init__.py", "file", b'__version__ = "2.2.0"\n', 0o644),
        (f"{root}/pyproject.toml", "file", b'[project]\nversion = "2.2.0"\n', 0o644),
    ]


def test_logical_identity_ignores_gzip_metadata_top_directory_and_member_order(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate.tar.gz"
    publication = tmp_path / "publication.tar.gz"
    candidate_entries = _valid_entries("candidate-build")
    publication_entries = _valid_entries("publication-build")
    _archive(candidate, candidate_entries, gzip_mtime=1)
    _archive(publication, list(reversed(publication_entries)), gzip_mtime=2_000_000_000)

    digest = compare_sdists(candidate, publication)

    assert digest == inspect_sdist(candidate).digest
    assert digest == inspect_sdist(publication).digest
    assert len(digest) == 64


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        ("content", b'__version__ = "9.9.9"\n', "changed in publication"),
        ("mode", 0o755, "changed in publication"),
    ],
)
def test_any_payload_change_fails(
    tmp_path: Path,
    field: str,
    replacement: bytes | int,
    message: str,
) -> None:
    candidate = tmp_path / "candidate.tar.gz"
    publication = tmp_path / "publication.tar.gz"
    entries = _valid_entries()
    mutated = list(entries)
    name, kind, content, mode = mutated[-1]
    if field == "content":
        content = replacement  # type: ignore[assignment]
    else:
        mode = replacement  # type: ignore[assignment]
    mutated[-1] = (name, kind, content, mode)
    _archive(candidate, entries)
    _archive(publication, mutated)

    with pytest.raises(SdistIdentityError, match=message):
        compare_sdists(candidate, publication)


@pytest.mark.parametrize(
    ("unsafe_path", "message"),
    [
        ("root/../escape.py", "traversal"),
        ("root/.hidden/./payload", "traversal"),
        (r"root\payload.py", "backslash"),
        ("/root/payload.py", "absolute"),
        ("root/path./payload.py", "Windows-ambiguous"),
        ("root/path /payload.py", "Windows-ambiguous"),
        ("root/C:/payload.py", "drive/stream"),
        ("root/NUL.txt", "device name"),
    ],
)
def test_unsafe_or_ambiguous_paths_fail(
    tmp_path: Path,
    unsafe_path: str,
    message: str,
) -> None:
    archive = tmp_path / "unsafe.tar.gz"
    _archive(archive, [(unsafe_path, "file", b"payload", 0o644)])

    with pytest.raises(SdistIdentityError, match=message):
        inspect_sdist(archive)


@pytest.mark.parametrize(
    "kind",
    ["symlink", "hardlink", "character-device"],
)
def test_links_and_devices_fail(tmp_path: Path, kind: str) -> None:
    archive = tmp_path / f"{kind}.tar.gz"
    _archive(archive, [("root/payload", kind, b"", 0o644)])

    with pytest.raises(SdistIdentityError, match="symlink/hardlink/device"):
        inspect_sdist(archive)


@pytest.mark.parametrize(
    "forbidden_path",
    [
        "root/.release/publish-2.2.0/candidate.json",
        "root/.RELEASE/publish-2.2.0/publication.json",
        "root/.release/publish-2.2.0/publication.json",
        "root/release-evidence/evidence.json",
        "root/Release-Evidence/evidence.json",
    ],
)
def test_markers_and_release_evidence_are_forbidden(
    tmp_path: Path,
    forbidden_path: str,
) -> None:
    archive = tmp_path / "forbidden.tar.gz"
    _archive(archive, [(forbidden_path, "file", b"{}\n", 0o644)])

    with pytest.raises(SdistIdentityError, match="forbidden release marker/evidence"):
        inspect_sdist(archive)


def test_casefold_duplicate_paths_fail_closed(tmp_path: Path) -> None:
    archive = tmp_path / "duplicate.tar.gz"
    _archive(
        archive,
        [
            ("root/Package.py", "file", b"one", 0o644),
            ("root/package.py", "file", b"two", 0o644),
        ],
    )

    with pytest.raises(SdistIdentityError, match="duplicate/Windows-colliding"):
        inspect_sdist(archive)


def test_duplicate_top_directory_entry_fails_closed(tmp_path: Path) -> None:
    archive = tmp_path / "duplicate-root.tar.gz"
    _archive(
        archive,
        [
            ("root", "directory", b"", 0o755),
            ("root", "directory", b"", 0o755),
            ("root/payload", "file", b"one", 0o644),
        ],
    )

    with pytest.raises(SdistIdentityError, match="duplicate normalized path"):
        inspect_sdist(archive)


def test_multiple_top_level_directories_fail(tmp_path: Path) -> None:
    archive = tmp_path / "two-roots.tar.gz"
    _archive(
        archive,
        [
            ("root-a/payload", "file", b"one", 0o644),
            ("root-b/payload", "file", b"two", 0o644),
        ],
    )

    with pytest.raises(SdistIdentityError, match="exactly one top-level directory"):
        inspect_sdist(archive)


def test_top_level_payload_without_wrapper_fails(tmp_path: Path) -> None:
    archive = tmp_path / "no-wrapper.tar.gz"
    _archive(archive, [("payload.py", "file", b"payload", 0o644)])

    with pytest.raises(SdistIdentityError, match="top-level sdist entry must be a directory"):
        inspect_sdist(archive)
