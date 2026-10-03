from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from tools.reconcile_release_2_2 import (
    ExpectedRelease,
    ReleaseReconciliationError,
    ReleaseSnapshot,
    load_expected_release,
    reconcile_after_reread,
    reconcile_release,
)
from tools.release_evidence_2_2 import logical_sdist_sha256, sha256_file, write_evidence

CANDIDATE_SOURCE = "1" * 40
CANDIDATE_MARKER = "2" * 40
PUBLICATION = "3" * 40


def _write_inputs(root: Path) -> ExpectedRelease:
    dist = root / "dist"
    dist.mkdir(parents=True)
    (dist / "swirengine-2.2.0-py3-none-any.whl").write_bytes(b"portable")
    (dist / "swirengine-2.2.0-cp314-cp314-win_amd64.whl").write_bytes(b"native")
    sdist = dist / "swirengine-2.2.0.tar.gz"
    with tarfile.open(sdist, mode="w:gz") as archive:
        content = b"source"
        info = tarfile.TarInfo("swirengine-2.2.0/src/swirengine/__init__.py")
        info.size = len(content)
        info.mode = 0o644
        archive.addfile(info, io.BytesIO(content))
    manifest = root / "manifest.json"
    manifest.write_text('{"required_workflows":["CI"]}\n', encoding="utf-8")
    write_evidence(
        dist,
        candidate_source_commit=CANDIDATE_SOURCE,
        candidate_marker_commit=CANDIDATE_MARKER,
        publication_commit=PUBLICATION,
        workflow_manifest=manifest,
        expected_workflow_manifest_sha256=sha256_file(manifest),
        expected_logical_sdist_sha256=logical_sdist_sha256(sdist),
    )
    return load_expected_release(dist, publication_commit=PUBLICATION)


def _pypi(expected: ExpectedRelease, names: set[str] | None = None) -> dict[str, object]:
    selected = (
        expected.distributions
        if names is None
        else tuple(item for item in expected.distributions if item.name in names)
    )
    return {
        "info": {"name": "swirengine", "version": "2.2.0"},
        "urls": [
            {
                "filename": item.name,
                "digests": {"sha256": item.sha256},
                "size": item.size,
                "yanked": False,
            }
            for item in selected
        ],
    }


def _tag(sha: str = PUBLICATION) -> dict[str, object]:
    return {
        "ref": "refs/tags/v2.2.0",
        "object": {"type": "commit", "sha": sha},
    }


def _release(
    expected: ExpectedRelease,
    names: set[str] | None = None,
    *,
    draft: bool = False,
    prerelease: bool = False,
) -> dict[str, object]:
    selected = (
        expected.release_assets
        if names is None
        else tuple(item for item in expected.release_assets if item.name in names)
    )
    return {
        "tag_name": "v2.2.0",
        "draft": draft,
        "prerelease": prerelease,
        "assets": [
            {
                "name": item.name,
                "digest": f"sha256:{item.sha256}",
                "size": item.size,
            }
            for item in selected
        ],
    }


def test_absent_state_plans_only_expected_creates_and_uploads(tmp_path: Path) -> None:
    expected = _write_inputs(tmp_path)

    plan = reconcile_release(expected, ReleaseSnapshot(pypi=None, tag=None, release=None))

    assert plan.pypi_uploads == tuple(item.name for item in expected.distributions)
    assert plan.github_uploads == tuple(item.name for item in expected.release_assets)
    assert plan.create_tag is True
    assert plan.create_release is True
    assert plan.complete is False


def test_complete_state_is_a_noop(tmp_path: Path) -> None:
    expected = _write_inputs(tmp_path)
    snapshot = ReleaseSnapshot(
        pypi=_pypi(expected),
        tag=_tag(),
        release=_release(expected),
    )

    plan = reconcile_release(expected, snapshot)

    assert plan.pypi_uploads == ()
    assert plan.github_uploads == ()
    assert plan.create_tag is False
    assert plan.create_release is False
    assert plan.complete is True


def test_partial_state_plans_only_missing_uploads(tmp_path: Path) -> None:
    expected = _write_inputs(tmp_path)
    present_distribution = expected.distributions[0].name
    present_asset = expected.release_assets[0].name
    snapshot = ReleaseSnapshot(
        pypi=_pypi(expected, {present_distribution}),
        tag=_tag(),
        release=_release(expected, {present_asset}),
    )

    plan = reconcile_release(expected, snapshot)

    assert set(plan.pypi_uploads) == {
        item.name for item in expected.distributions if item.name != present_distribution
    }
    assert set(plan.github_uploads) == {
        item.name for item in expected.release_assets if item.name != present_asset
    }
    assert plan.create_tag is False
    assert plan.create_release is False


@pytest.mark.parametrize("field", ["sha256", "size"])
def test_pypi_identity_mismatch_fails_closed(tmp_path: Path, field: str) -> None:
    expected = _write_inputs(tmp_path)
    payload = _pypi(expected)
    first = payload["urls"][0]  # type: ignore[index]
    if field == "sha256":
        first["digests"]["sha256"] = "f" * 64  # type: ignore[index]
    else:
        first["size"] += 1  # type: ignore[operator]

    with pytest.raises(ReleaseReconciliationError, match="identity mismatch"):
        reconcile_release(
            expected,
            ReleaseSnapshot(pypi=payload, tag=_tag(), release=_release(expected)),
        )


def test_yanked_pypi_distribution_fails_closed(tmp_path: Path) -> None:
    expected = _write_inputs(tmp_path)
    payload = _pypi(expected)
    payload["urls"][0]["yanked"] = True  # type: ignore[index]

    with pytest.raises(ReleaseReconciliationError, match="is yanked"):
        reconcile_release(
            expected,
            ReleaseSnapshot(pypi=payload, tag=_tag(), release=_release(expected)),
        )


@pytest.mark.parametrize("field", ["digest", "size"])
def test_github_asset_identity_mismatch_fails_closed(tmp_path: Path, field: str) -> None:
    expected = _write_inputs(tmp_path)
    release = _release(expected)
    first = release["assets"][0]  # type: ignore[index]
    if field == "digest":
        first[field] = f"sha256:{'f' * 64}"  # type: ignore[index]
    else:
        first[field] += 1  # type: ignore[operator]

    with pytest.raises(ReleaseReconciliationError, match="identity mismatch"):
        reconcile_release(
            expected,
            ReleaseSnapshot(pypi=_pypi(expected), tag=_tag(), release=release),
        )


@pytest.mark.parametrize("target", ["pypi", "github"])
def test_extra_remote_artifact_fails_closed(tmp_path: Path, target: str) -> None:
    expected = _write_inputs(tmp_path)
    pypi = _pypi(expected)
    release = _release(expected)
    extra = {"size": 1}
    if target == "pypi":
        extra.update(
            {
                "filename": "extra.whl",
                "digests": {"sha256": "e" * 64},
                "yanked": False,
            }
        )
        pypi["urls"].append(extra)  # type: ignore[union-attr]
    else:
        extra.update({"name": "extra.txt", "digest": f"sha256:{'e' * 64}"})
        release["assets"].append(extra)  # type: ignore[union-attr]

    with pytest.raises(ReleaseReconciliationError, match="unexpected extra"):
        reconcile_release(
            expected,
            ReleaseSnapshot(pypi=pypi, tag=_tag(), release=release),
        )


@pytest.mark.parametrize("target", ["pypi", "github"])
def test_duplicate_remote_artifact_is_ambiguous(tmp_path: Path, target: str) -> None:
    expected = _write_inputs(tmp_path)
    pypi = _pypi(expected)
    release = _release(expected)
    if target == "pypi":
        pypi["urls"].append(dict(pypi["urls"][0]))  # type: ignore[index,union-attr]
    else:
        release["assets"].append(dict(release["assets"][0]))  # type: ignore[index,union-attr]

    with pytest.raises(ReleaseReconciliationError, match="ambiguous duplicate"):
        reconcile_release(
            expected,
            ReleaseSnapshot(pypi=pypi, tag=_tag(), release=release),
        )


def test_wrong_tag_target_fails_closed(tmp_path: Path) -> None:
    expected = _write_inputs(tmp_path)

    with pytest.raises(ReleaseReconciliationError, match="exact publication commit"):
        reconcile_release(
            expected,
            ReleaseSnapshot(
                pypi=_pypi(expected),
                tag=_tag("0" * 40),
                release=_release(expected),
            ),
        )


@pytest.mark.parametrize(
    ("draft", "prerelease", "message"),
    [(True, False, "draft"), (False, True, "prerelease")],
)
def test_non_final_github_release_fails_closed(
    tmp_path: Path,
    draft: bool,
    prerelease: bool,
    message: str,
) -> None:
    expected = _write_inputs(tmp_path)

    with pytest.raises(ReleaseReconciliationError, match=message):
        reconcile_release(
            expected,
            ReleaseSnapshot(
                pypi=_pypi(expected),
                tag=_tag(),
                release=_release(expected, draft=draft, prerelease=prerelease),
            ),
        )


def test_release_without_exact_tag_fails_closed(tmp_path: Path) -> None:
    expected = _write_inputs(tmp_path)

    with pytest.raises(ReleaseReconciliationError, match="tag snapshot is absent"):
        reconcile_release(
            expected,
            ReleaseSnapshot(
                pypi=_pypi(expected),
                tag=None,
                release=_release(expected),
            ),
        )


def test_reread_accepts_only_monotonic_progress(tmp_path: Path) -> None:
    expected = _write_inputs(tmp_path)
    initial = ReleaseSnapshot(pypi=None, tag=None, release=None)
    pypi_name = expected.distributions[0].name
    github_name = expected.release_assets[0].name
    reread = ReleaseSnapshot(
        pypi=_pypi(expected, {pypi_name}),
        tag=_tag(),
        release=_release(expected, {github_name}),
    )

    plan = reconcile_after_reread(expected, initial, reread)

    assert pypi_name not in plan.pypi_uploads
    assert github_name not in plan.github_uploads
    assert plan.create_tag is False
    assert plan.create_release is False


def test_reread_rejects_remote_regression(tmp_path: Path) -> None:
    expected = _write_inputs(tmp_path)
    complete = ReleaseSnapshot(
        pypi=_pypi(expected),
        tag=_tag(),
        release=_release(expected),
    )
    partial = ReleaseSnapshot(
        pypi=_pypi(expected, {expected.distributions[0].name}),
        tag=_tag(),
        release=_release(expected),
    )

    with pytest.raises(ReleaseReconciliationError, match="regressed"):
        reconcile_after_reread(expected, complete, partial)
