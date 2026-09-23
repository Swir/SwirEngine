from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

EXPECTED_PACKAGE = "swirengine"
EXPECTED_VERSION = "2.1.0"
SCHEMA = "swirengine-release-provenance-v1"
CHECKSUMS_NAME = "SHA256SUMS"
PROVENANCE_NAME = "release-provenance.json"
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _candidate_artifacts(dist_dir: Path) -> list[Path]:
    artifacts = sorted(
        [
            *dist_dir.glob(f"{EXPECTED_PACKAGE}-{EXPECTED_VERSION}-*.whl"),
            *dist_dir.glob(f"{EXPECTED_PACKAGE}-{EXPECTED_VERSION}.tar.gz"),
        ],
        key=lambda path: path.name,
    )
    return [path for path in artifacts if path.is_file()]


def _validate_artifact_set(
    artifacts: list[Path], *, require_windows_cp314: bool
) -> list[str]:
    errors: list[str] = []
    names = [path.name for path in artifacts]
    portable = f"{EXPECTED_PACKAGE}-{EXPECTED_VERSION}-py3-none-any.whl"
    sdist = f"{EXPECTED_PACKAGE}-{EXPECTED_VERSION}.tar.gz"
    if portable not in names:
        errors.append(f"missing portable wheel: {portable}")
    if sdist not in names:
        errors.append(f"missing source distribution: {sdist}")
    if require_windows_cp314:
        native = f"{EXPECTED_PACKAGE}-{EXPECTED_VERSION}-cp314-cp314-win_amd64.whl"
        if native not in names:
            errors.append(f"missing Windows CPython 3.14 wheel: {native}")
    if len(names) != len(set(names)):
        errors.append("candidate artifact names must be unique")
    return errors


def build_provenance(
    dist_dir: Path,
    source_sha: str,
    *,
    require_windows_cp314: bool = False,
) -> dict[str, Any]:
    source_sha = source_sha.lower()
    if not _SHA_RE.fullmatch(source_sha):
        raise ValueError("source SHA must be exactly 40 lowercase hexadecimal characters")

    artifacts = _candidate_artifacts(dist_dir)
    errors = _validate_artifact_set(
        artifacts, require_windows_cp314=require_windows_cp314
    )
    if errors:
        raise ValueError("; ".join(errors))

    return {
        "schema": SCHEMA,
        "package": EXPECTED_PACKAGE,
        "version": EXPECTED_VERSION,
        "source_commit": source_sha,
        "hash_algorithm": "sha256",
        "artifacts": [
            {
                "name": path.name,
                "sha256": _sha256(path),
                "size": path.stat().st_size,
            }
            for path in artifacts
        ],
    }


def render_checksums(provenance: dict[str, Any]) -> str:
    return "".join(
        f"{artifact['sha256']}  {artifact['name']}\n"
        for artifact in provenance["artifacts"]
    )


def write_evidence(
    dist_dir: Path,
    source_sha: str,
    *,
    require_windows_cp314: bool = False,
) -> tuple[Path, Path]:
    provenance = build_provenance(
        dist_dir,
        source_sha,
        require_windows_cp314=require_windows_cp314,
    )
    checksums_path = dist_dir / CHECKSUMS_NAME
    provenance_path = dist_dir / PROVENANCE_NAME
    checksums_path.write_text(render_checksums(provenance), encoding="utf-8")
    provenance_path.write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return checksums_path, provenance_path


def verify_evidence(
    dist_dir: Path,
    source_sha: str,
    *,
    require_windows_cp314: bool = False,
) -> list[str]:
    expected = build_provenance(
        dist_dir,
        source_sha,
        require_windows_cp314=require_windows_cp314,
    )
    errors: list[str] = []

    checksums_path = dist_dir / CHECKSUMS_NAME
    provenance_path = dist_dir / PROVENANCE_NAME
    if not checksums_path.is_file():
        errors.append(f"missing {CHECKSUMS_NAME}")
    if not provenance_path.is_file():
        errors.append(f"missing {PROVENANCE_NAME}")
    if errors:
        return errors

    try:
        actual = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        errors.append(f"invalid {PROVENANCE_NAME}: {exc}")
        actual = None

    if actual != expected:
        errors.append("release provenance does not match exact candidate artifacts/source")

    expected_checksums = render_checksums(expected)
    actual_checksums = checksums_path.read_text(encoding="utf-8")
    if actual_checksums != expected_checksums:
        errors.append("SHA256SUMS does not match exact candidate artifacts")

    return errors


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate or verify deterministic SwirEngine 2.1 candidate release evidence."
    )
    parser.add_argument("mode", choices=("generate", "verify"))
    parser.add_argument("--dist-dir", type=Path, default=Path("dist"))
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--require-windows-cp314", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    dist_dir = args.dist_dir
    if not dist_dir.is_dir():
        print(f"SwirEngine 2.1 release evidence FAILED: missing dist directory: {dist_dir}")
        return 1

    try:
        if args.mode == "generate":
            checksums, provenance = write_evidence(
                dist_dir,
                args.source_sha,
                require_windows_cp314=args.require_windows_cp314,
            )
            print(f"wrote {checksums}")
            print(f"wrote {provenance}")
            return 0

        errors = verify_evidence(
            dist_dir,
            args.source_sha,
            require_windows_cp314=args.require_windows_cp314,
        )
    except ValueError as exc:
        print(f"SwirEngine 2.1 release evidence FAILED: {exc}")
        return 1

    if errors:
        print("SwirEngine 2.1 release evidence verification FAILED:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("SwirEngine 2.1 release evidence verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
