from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from tools.verify_distribution_audit_data_2_2 import (
    DistributionAuditDataError,
    inspect_distributions,
    verify_pyproject_guard,
)

SAFE_WHEEL_MEMBER = "swirengine/__init__.py"
SAFE_SDIST_MEMBER = "swirengine-2.2.0/src/swirengine/__init__.py"


def _write_wheel(path: Path, members: tuple[str, ...]) -> None:
    with zipfile.ZipFile(path, mode="w") as archive:
        for name in members:
            archive.writestr(name, b"fixture")


def _write_sdist(path: Path, members: tuple[str, ...]) -> None:
    with tarfile.open(path, mode="w:gz") as archive:
        for name in members:
            payload = b"fixture"
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))


def _write_pair(
    root: Path,
    *,
    wheel_members: tuple[str, ...] = (SAFE_WHEEL_MEMBER,),
    sdist_members: tuple[str, ...] = (SAFE_SDIST_MEMBER,),
) -> None:
    _write_wheel(root / "swirengine-2.2.0-py3-none-any.whl", wheel_members)
    _write_sdist(root / "swirengine-2.2.0.tar.gz", sdist_members)


def _write_pair_with_member(root: Path, archive_kind: str, member: str) -> None:
    if archive_kind == "wheel":
        _write_pair(root, wheel_members=(SAFE_WHEEL_MEMBER, member))
        return
    assert archive_kind == "sdist"
    _write_pair(root, sdist_members=(SAFE_SDIST_MEMBER, member))


def test_pyproject_guard_accepts_exact_distribution_policy(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[tool.hatch.build.targets.wheel]
packages = ["src/swirengine"]

[tool.hatch.build.targets.sdist]
exclude = ["/release-evidence", "/.release"]
""".strip(),
        encoding="utf-8",
    )

    verify_pyproject_guard(tmp_path)


@pytest.mark.parametrize(
    "content",
    [
        """
[tool.hatch.build.targets.wheel]
packages = ["src/swirengine"]
""",
        """
[tool.hatch.build.targets.wheel]
packages = ["src/swirengine"]
[tool.hatch.build.targets.sdist]
exclude = ["/release-evidence"]
""",
        """
[tool.hatch.build.targets.wheel]
packages = ["src"]
[tool.hatch.build.targets.sdist]
exclude = ["/release-evidence", "/.release"]
""",
    ],
)
def test_pyproject_guard_rejects_missing_or_changed_policy(
    tmp_path: Path, content: str
) -> None:
    (tmp_path / "pyproject.toml").write_text(content.strip(), encoding="utf-8")

    with pytest.raises(DistributionAuditDataError):
        verify_pyproject_guard(tmp_path)


def test_inspection_accepts_clean_distribution_pair(tmp_path: Path) -> None:
    _write_pair(tmp_path)

    inspect_distributions(tmp_path)


def test_wheel_only_inspection_accepts_exact_vendored_wheel(tmp_path: Path) -> None:
    _write_wheel(
        tmp_path / "swirengine-2.2.0-cp314-cp314-win_amd64.whl",
        (SAFE_WHEEL_MEMBER,),
    )

    inspect_distributions(tmp_path, wheel_only=True)


@pytest.mark.parametrize("extra", ["wheel", "sdist"])
def test_wheel_only_inspection_rejects_non_exact_inventory(
    tmp_path: Path, extra: str
) -> None:
    _write_wheel(
        tmp_path / "swirengine-2.2.0-cp314-cp314-win_amd64.whl",
        (SAFE_WHEEL_MEMBER,),
    )
    if extra == "wheel":
        _write_wheel(
            tmp_path / "swirengine-2.2.0-py3-none-any.whl",
            (SAFE_WHEEL_MEMBER,),
        )
    else:
        _write_sdist(tmp_path / "swirengine-2.2.0.tar.gz", (SAFE_SDIST_MEMBER,))

    with pytest.raises(DistributionAuditDataError, match="wheel only"):
        inspect_distributions(tmp_path, wheel_only=True)


def test_wheel_only_inspection_rejects_repository_audit_data(tmp_path: Path) -> None:
    _write_wheel(
        tmp_path / "swirengine-2.2.0-cp314-cp314-win_amd64.whl",
        (SAFE_WHEEL_MEMBER, "swirengine/release-evidence/proof.json"),
    )

    with pytest.raises(DistributionAuditDataError, match="release-evidence"):
        inspect_distributions(tmp_path, wheel_only=True)


@pytest.mark.parametrize("archive_kind", ["wheel", "sdist"])
def test_inspection_rejects_release_evidence_in_both_archive_types(
    tmp_path: Path, archive_kind: str
) -> None:
    _write_pair_with_member(
        tmp_path,
        archive_kind,
        r"root\RELEASE-EVIDENCE\proof.json",
    )

    with pytest.raises(DistributionAuditDataError, match="release-evidence"):
        inspect_distributions(tmp_path)


@pytest.mark.parametrize("archive_kind", ["wheel", "sdist"])
def test_v8_rejects_publication_marker_in_both_archive_types(
    tmp_path: Path, archive_kind: str
) -> None:
    _write_pair_with_member(
        tmp_path,
        archive_kind,
        "root/.release/publish-2.2.0",
    )

    with pytest.raises(DistributionAuditDataError, match="publication-control marker"):
        inspect_distributions(tmp_path)


@pytest.mark.parametrize("archive_kind", ["wheel", "sdist"])
def test_rejects_historical_release_control_in_both_archive_types(
    tmp_path: Path, archive_kind: str
) -> None:
    _write_pair_with_member(
        tmp_path,
        archive_kind,
        "root/.release/publish-2.1.0",
    )

    with pytest.raises(DistributionAuditDataError, match="publication-control marker"):
        inspect_distributions(tmp_path)


@pytest.mark.parametrize("archive_kind", ["wheel", "sdist"])
def test_v9_rejects_publication_marker_sequence_before_a_child(
    tmp_path: Path, archive_kind: str
) -> None:
    _write_pair_with_member(
        tmp_path,
        archive_kind,
        "root/.release/publish-2.2.0/child.txt",
    )

    with pytest.raises(DistributionAuditDataError, match="publication-control marker"):
        inspect_distributions(tmp_path)


@pytest.mark.parametrize("archive_kind", ["wheel", "sdist"])
def test_v10_rejects_parent_traversal_before_marker_matching(
    tmp_path: Path, archive_kind: str
) -> None:
    _write_pair_with_member(
        tmp_path,
        archive_kind,
        "root/.release/x/../publish-2.2.0",
    )

    with pytest.raises(DistributionAuditDataError, match="parent traversal"):
        inspect_distributions(tmp_path)


@pytest.mark.parametrize(
    ("archive_kind", "member"),
    [
        ("wheel", "root/.release./publish-2.2.0/child.txt"),
        ("sdist", "root/.release./publish-2.2.0/child.txt"),
        ("wheel", "root/release-evidence /proof.json"),
        ("sdist", "root/release-evidence /proof.json"),
    ],
)
def test_v11_rejects_windows_trailing_dot_or_space(
    tmp_path: Path, archive_kind: str, member: str
) -> None:
    _write_pair_with_member(tmp_path, archive_kind, member)

    with pytest.raises(DistributionAuditDataError, match="Windows-ambiguous"):
        inspect_distributions(tmp_path)


@pytest.mark.parametrize(
    ("archive_kind", "member", "message"),
    [
        ("sdist", "root/publication-dist/swirengine-2.2.0-py3-none-any.whl", "nested"),
        ("wheel", "root/.pytest_cache/state", "cache"),
        ("sdist", "root/tools/__pycache__/verify.cpython-313.pyc", "cache"),
        ("wheel", "root/swirengine/generated.pyo", "bytecode"),
    ],
)
def test_rejects_nested_build_outputs_and_caches(
    tmp_path: Path, archive_kind: str, member: str, message: str
) -> None:
    _write_pair_with_member(tmp_path, archive_kind, member)

    with pytest.raises(DistributionAuditDataError, match=message):
        inspect_distributions(tmp_path)


@pytest.mark.parametrize(
    "member",
    [
        "root/release-evidence-old/proof.json",
        "root/.release-notes/publish-2.2.0/child.txt",
        "root/release/publish-2.2.0-notes/child.txt",
        "root/name.with.internal.dots/file with internal spaces.txt",
    ],
)
def test_inspection_accepts_safe_lookalikes(tmp_path: Path, member: str) -> None:
    _write_pair(
        tmp_path,
        wheel_members=(SAFE_WHEEL_MEMBER, member),
        sdist_members=(SAFE_SDIST_MEMBER, member),
    )

    inspect_distributions(tmp_path)
