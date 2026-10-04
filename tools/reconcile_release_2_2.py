from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from tools.release_evidence_2_2 import (
        CHECKSUMS_NAME,
        EXPECTED_DISTRIBUTIONS,
        EXPECTED_PACKAGE,
        EXPECTED_VERSION,
        PROVENANCE_NAME,
        SCHEMA,
        render_checksums,
        sha256_file,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from release_evidence_2_2 import (
        CHECKSUMS_NAME,
        EXPECTED_DISTRIBUTIONS,
        EXPECTED_PACKAGE,
        EXPECTED_VERSION,
        PROVENANCE_NAME,
        SCHEMA,
        render_checksums,
        sha256_file,
    )

TAG = f"v{EXPECTED_VERSION}"
EXPECTED_RELEASE_TITLE = f"SwirEngine {EXPECTED_VERSION}"
DEFAULT_RELEASE_NOTES = Path(__file__).resolve().parents[1] / "RELEASE_NOTES_2_2.md"
EXPECTED_PROVENANCE_KEYS = {
    "schema",
    "package",
    "version",
    "candidate_source_commit",
    "candidate_marker_commit",
    "publication_commit",
    "hash_algorithm",
    "workflow_manifest_sha256",
    "logical_sdist_sha256",
    "artifacts",
}
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ReleaseReconciliationError(ValueError):
    """Raised when a release snapshot is unsafe or ambiguous to resume."""


@dataclass(frozen=True, slots=True, order=True)
class ArtifactIdentity:
    name: str
    sha256: str
    size: int

    def as_dict(self) -> dict[str, str | int]:
        return {"name": self.name, "sha256": self.sha256, "size": self.size}


@dataclass(frozen=True, slots=True)
class ExpectedRelease:
    publication_commit: str
    release_title: str
    release_body: str
    distributions: tuple[ArtifactIdentity, ...]
    release_assets: tuple[ArtifactIdentity, ...]


@dataclass(frozen=True, slots=True)
class ReleaseSnapshot:
    pypi: object | None
    tag: object | None
    release: object | None


@dataclass(frozen=True, slots=True)
class ReconciliationPlan:
    pypi_uploads: tuple[str, ...]
    github_uploads: tuple[str, ...]
    create_tag: bool
    create_release: bool

    @property
    def complete(self) -> bool:
        return not (
            self.pypi_uploads
            or self.github_uploads
            or self.create_tag
            or self.create_release
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "complete": self.complete,
            "create_release": self.create_release,
            "create_tag": self.create_tag,
            "github_uploads": list(self.github_uploads),
            "pypi_uploads": list(self.pypi_uploads),
        }


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReleaseReconciliationError(message)


def _identity(name: object, sha256: object, size: object, *, source: str) -> ArtifactIdentity:
    _require(isinstance(name, str) and bool(name), f"{source} artifact name must be non-empty")
    _require(
        isinstance(sha256, str) and bool(_SHA256_RE.fullmatch(sha256)),
        f"{source} artifact {name!r} has no canonical SHA-256 digest",
    )
    _require(
        isinstance(size, int) and not isinstance(size, bool) and size >= 0,
        f"{source} artifact {name!r} has no valid size",
    )
    return ArtifactIdentity(name=name, sha256=sha256, size=size)


def _remote_digest(item: Mapping[str, Any], *, source: str, name: object) -> object:
    direct = item.get("sha256")
    if direct is not None:
        return direct
    digests = item.get("digests")
    if isinstance(digests, Mapping) and digests.get("sha256") is not None:
        return digests.get("sha256")
    digest = item.get("digest")
    if isinstance(digest, str) and digest.startswith("sha256:"):
        return digest.removeprefix("sha256:")
    raise ReleaseReconciliationError(
        f"{source} artifact {name!r} has no authoritative SHA-256 digest"
    )


def _remote_identities(
    values: object,
    *,
    source: str,
    name_field: str,
) -> tuple[ArtifactIdentity, ...]:
    _require(isinstance(values, list), f"{source} artifacts must be a JSON array")
    identities: list[ArtifactIdentity] = []
    names: set[str] = set()
    for index, item in enumerate(values):
        _require(isinstance(item, Mapping), f"{source} artifact {index} must be an object")
        assert isinstance(item, Mapping)
        name = item.get(name_field)
        identity = _identity(
            name,
            _remote_digest(item, source=source, name=name),
            item.get("size"),
            source=source,
        )
        _require(
            identity.name not in names,
            f"{source} has ambiguous duplicate artifact name: {identity.name}",
        )
        names.add(identity.name)
        identities.append(identity)
    return tuple(sorted(identities))


def _local_identity(path: Path) -> ArtifactIdentity:
    _require(path.is_file(), f"local release asset is missing: {path.name}")
    return ArtifactIdentity(name=path.name, sha256=sha256_file(path), size=path.stat().st_size)


def load_expected_release(
    dist_dir: Path,
    *,
    publication_commit: str,
    release_notes: Path = DEFAULT_RELEASE_NOTES,
) -> ExpectedRelease:
    _require(
        bool(_COMMIT_RE.fullmatch(publication_commit)),
        "publication commit must be exactly 40 lowercase hexadecimal characters",
    )
    provenance_path = dist_dir / PROVENANCE_NAME
    checksums_path = dist_dir / CHECKSUMS_NAME
    _require(provenance_path.is_file(), f"local release asset is missing: {PROVENANCE_NAME}")
    _require(checksums_path.is_file(), f"local release asset is missing: {CHECKSUMS_NAME}")
    _require(
        release_notes.is_file() and not release_notes.is_symlink(),
        f"release notes are missing or unsafe: {release_notes}",
    )
    try:
        release_body = release_notes.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ReleaseReconciliationError(f"cannot read release notes: {exc}") from exc
    _require(bool(release_body), "release notes must not be empty")
    try:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ReleaseReconciliationError(f"invalid {PROVENANCE_NAME}: {exc}") from exc
    _require(isinstance(provenance, Mapping), f"{PROVENANCE_NAME} must contain an object")
    assert isinstance(provenance, Mapping)
    _require(
        set(provenance) == EXPECTED_PROVENANCE_KEYS,
        f"{PROVENANCE_NAME} does not use the exact v2 schema",
    )
    _require(provenance.get("schema") == SCHEMA, "unexpected provenance schema")
    _require(provenance.get("package") == EXPECTED_PACKAGE, "unexpected provenance package")
    _require(provenance.get("version") == EXPECTED_VERSION, "unexpected provenance version")
    _require(provenance.get("hash_algorithm") == "sha256", "unexpected hash algorithm")
    _require(
        provenance.get("publication_commit") == publication_commit,
        "provenance publication commit does not match the exact tag target",
    )
    for field in (
        "candidate_source_commit",
        "candidate_marker_commit",
        "publication_commit",
    ):
        _require(
            isinstance(provenance.get(field), str)
            and bool(_COMMIT_RE.fullmatch(str(provenance[field]))),
            f"provenance {field} is not a canonical commit",
        )
    for field in ("workflow_manifest_sha256", "logical_sdist_sha256"):
        _require(
            isinstance(provenance.get(field), str)
            and bool(_SHA256_RE.fullmatch(str(provenance[field]))),
            f"provenance {field} is not a canonical SHA-256 digest",
        )

    artifacts = provenance.get("artifacts")
    _require(isinstance(artifacts, list), "provenance artifacts must be an array")
    distributions: list[ArtifactIdentity] = []
    names: set[str] = set()
    for index, item in enumerate(artifacts):
        _require(isinstance(item, Mapping), f"provenance artifact {index} must be an object")
        assert isinstance(item, Mapping)
        _require(
            set(item) == {"name", "sha256", "size"},
            f"provenance artifact {index} has an invalid schema",
        )
        identity = _identity(
            item.get("name"),
            item.get("sha256"),
            item.get("size"),
            source="provenance",
        )
        _require(
            identity.name not in names,
            f"provenance has ambiguous duplicate artifact name: {identity.name}",
        )
        names.add(identity.name)
        distributions.append(identity)
    distributions.sort()
    _require(
        tuple(item.name for item in distributions) == tuple(sorted(EXPECTED_DISTRIBUTIONS)),
        "provenance does not contain the exact three 2.2.0 distributions",
    )
    for identity in distributions:
        actual = _local_identity(dist_dir / identity.name)
        _require(actual == identity, f"local distribution differs from provenance: {identity.name}")
    _require(
        checksums_path.read_text(encoding="utf-8") == render_checksums(provenance),
        f"{CHECKSUMS_NAME} does not match provenance",
    )

    evidence = (_local_identity(checksums_path), _local_identity(provenance_path))
    return ExpectedRelease(
        publication_commit=publication_commit,
        release_title=EXPECTED_RELEASE_TITLE,
        release_body=release_body,
        distributions=tuple(distributions),
        release_assets=tuple(sorted((*distributions, *evidence))),
    )


def _missing_only(
    expected: tuple[ArtifactIdentity, ...],
    actual: tuple[ArtifactIdentity, ...],
    *,
    source: str,
) -> tuple[str, ...]:
    expected_by_name = {item.name: item for item in expected}
    actual_by_name = {item.name: item for item in actual}
    extra = sorted(set(actual_by_name) - set(expected_by_name))
    _require(not extra, f"{source} has unexpected extra artifacts: {extra!r}")
    for name, identity in actual_by_name.items():
        _require(
            identity == expected_by_name[name],
            f"{source} artifact identity mismatch for {name}: "
            f"remote={identity.as_dict()!r}, expected={expected_by_name[name].as_dict()!r}",
        )
    return tuple(sorted(set(expected_by_name) - set(actual_by_name)))


def _pypi_identities(payload: object | None) -> tuple[ArtifactIdentity, ...]:
    if payload is None:
        return ()
    _require(isinstance(payload, Mapping), "PyPI snapshot must be an object or null")
    assert isinstance(payload, Mapping)
    info = payload.get("info")
    _require(isinstance(info, Mapping), "PyPI snapshot has no info object")
    assert isinstance(info, Mapping)
    _require(info.get("name") == EXPECTED_PACKAGE, "PyPI snapshot has an unexpected package")
    _require(info.get("version") == EXPECTED_VERSION, "PyPI snapshot has an unexpected version")
    urls = payload.get("urls")
    _require(isinstance(urls, list), "PyPI artifacts must be a JSON array")
    for index, item in enumerate(urls):
        _require(isinstance(item, Mapping), f"PyPI artifact {index} must be an object")
        assert isinstance(item, Mapping)
        _require(
            item.get("yanked") is False,
            f"PyPI artifact {item.get('filename')!r} is yanked or lacks explicit yanked=false",
        )
    return _remote_identities(
        urls,
        source="PyPI",
        name_field="filename",
    )


def _validate_tag(payload: object | None, *, publication_commit: str) -> bool:
    if payload is None:
        return False
    _require(isinstance(payload, Mapping), "GitHub tag snapshot must be an object or null")
    assert isinstance(payload, Mapping)
    _require(payload.get("ref") == f"refs/tags/{TAG}", "GitHub tag snapshot has wrong ref")
    target = payload.get("object")
    _require(isinstance(target, Mapping), "GitHub tag snapshot has no object")
    assert isinstance(target, Mapping)
    _require(target.get("type") == "commit", "GitHub tag must resolve directly to a commit")
    _require(
        target.get("sha") == publication_commit,
        "GitHub tag does not target the exact publication commit",
    )
    return True


def _release_identities(
    payload: object | None,
    *,
    expected: ExpectedRelease,
) -> tuple[ArtifactIdentity, ...] | None:
    if payload is None:
        return None
    _require(isinstance(payload, Mapping), "GitHub Release snapshot must be an object or null")
    assert isinstance(payload, Mapping)
    _require(payload.get("tag_name") == TAG, "GitHub Release has an unexpected tag")
    _require(
        payload.get("name") == expected.release_title,
        "GitHub Release has an unexpected title",
    )
    _require(
        payload.get("body") == expected.release_body,
        "GitHub Release notes do not match the exact release notes",
    )
    _require(payload.get("draft") is False, "GitHub Release must not be a draft")
    _require(payload.get("prerelease") is False, "GitHub Release must not be a prerelease")
    _require(
        payload.get("immutable") is True,
        "GitHub Release must be server-enforced immutable",
    )
    return _remote_identities(
        payload.get("assets"),
        source="GitHub Release",
        name_field="name",
    )


def reconcile_release(
    expected: ExpectedRelease,
    snapshot: ReleaseSnapshot,
) -> ReconciliationPlan:
    pypi = _pypi_identities(snapshot.pypi)
    tag_exists = _validate_tag(snapshot.tag, publication_commit=expected.publication_commit)
    release = _release_identities(snapshot.release, expected=expected)
    _require(
        release is None or tag_exists,
        "GitHub Release exists while the exact tag snapshot is absent",
    )
    pypi_uploads = _missing_only(expected.distributions, pypi, source="PyPI")
    if release is None:
        github_uploads = tuple(item.name for item in expected.release_assets)
    else:
        missing_release_assets = _missing_only(
            expected.release_assets,
            release,
            source="GitHub Release",
        )
        _require(
            not missing_release_assets,
            "immutable GitHub Release is incomplete and cannot accept missing assets: "
            f"{list(missing_release_assets)!r}",
        )
        github_uploads = ()
    return ReconciliationPlan(
        pypi_uploads=pypi_uploads,
        github_uploads=github_uploads,
        create_tag=not tag_exists,
        create_release=release is None,
    )


def reconcile_after_reread(
    expected: ExpectedRelease,
    initial: ReleaseSnapshot,
    reread: ReleaseSnapshot,
) -> ReconciliationPlan:
    """Accept only monotonic progress between the initial read and immediate re-read."""

    before = reconcile_release(expected, initial)
    after = reconcile_release(expected, reread)
    _require(
        set(after.pypi_uploads).issubset(before.pypi_uploads),
        "PyPI state regressed between initial read and re-read",
    )
    _require(
        set(after.github_uploads).issubset(before.github_uploads),
        "GitHub Release state regressed between initial read and re-read",
    )
    _require(
        not after.create_tag or before.create_tag,
        "GitHub tag disappeared between initial read and re-read",
    )
    _require(
        not after.create_release or before.create_release,
        "GitHub Release disappeared between initial read and re-read",
    )
    return after


def _load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ReleaseReconciliationError(f"cannot read JSON snapshot {path}: {exc}") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Plan a fail-closed SwirEngine 2.2 release retry from saved JSON snapshots; "
            "this command performs no network mutation."
        ),
    )
    parser.add_argument("--dist-dir", type=Path, default=Path("dist"))
    parser.add_argument("--publication-commit", required=True)
    parser.add_argument("--pypi-json", type=Path, required=True)
    parser.add_argument("--tag-json", type=Path, required=True)
    parser.add_argument("--release-json", type=Path, required=True)
    parser.add_argument("--release-notes", type=Path, default=DEFAULT_RELEASE_NOTES)
    parser.add_argument("--initial-pypi-json", type=Path)
    parser.add_argument("--initial-tag-json", type=Path)
    parser.add_argument("--initial-release-json", type=Path)
    parser.add_argument("--require-complete", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    initial_paths = (
        args.initial_pypi_json,
        args.initial_tag_json,
        args.initial_release_json,
    )
    if any(path is not None for path in initial_paths) and not all(
        path is not None for path in initial_paths
    ):
        parser.error(
            "--initial-pypi-json, --initial-tag-json and --initial-release-json "
            "must be supplied together"
        )
    try:
        expected = load_expected_release(
            args.dist_dir,
            publication_commit=args.publication_commit,
            release_notes=args.release_notes,
        )
        fresh = ReleaseSnapshot(
            pypi=_load_json(args.pypi_json),
            tag=_load_json(args.tag_json),
            release=_load_json(args.release_json),
        )
        if all(path is not None for path in initial_paths):
            initial = ReleaseSnapshot(
                pypi=_load_json(args.initial_pypi_json),
                tag=_load_json(args.initial_tag_json),
                release=_load_json(args.initial_release_json),
            )
            plan = reconcile_after_reread(expected, initial, fresh)
        else:
            plan = reconcile_release(expected, fresh)
    except (OSError, ReleaseReconciliationError) as exc:
        print(f"SwirEngine 2.2 release reconciliation FAILED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(plan.as_dict(), sort_keys=True, separators=(",", ":")))
    if args.require_complete and not plan.complete:
        print("SwirEngine 2.2 release reconciliation is incomplete", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
