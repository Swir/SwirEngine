from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tarfile
import unicodedata
from collections.abc import Mapping, Sequence
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

WINDOWS_DEVICE_RE = re.compile(
    r"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$",
    re.IGNORECASE,
)
FORBIDDEN_ROOTS = {".release", "release-evidence"}
FORBIDDEN_ROOT_KEYS = {name.casefold() for name in FORBIDDEN_ROOTS}


class SdistIdentityError(ValueError):
    """Raised when an sdist is unsafe or the two logical payloads differ."""


@dataclass(frozen=True, slots=True)
class LogicalEntry:
    kind: str
    mode: int
    size: int
    sha256: str | None


@dataclass(frozen=True, slots=True)
class LogicalSdist:
    source: Path
    top_directory: str
    entries: Mapping[str, LogicalEntry]
    digest: str


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SdistIdentityError(message)


def _safe_components(name: str, *, source: Path) -> tuple[str, ...]:
    subject = f"{source.name}:{name!r}"
    _require(bool(name), f"empty archive path in {source.name}")
    _require("\x00" not in name, f"NUL in archive path {subject}")
    _require("\\" not in name, f"backslash is forbidden in archive path {subject}")
    _require(not name.startswith("/"), f"absolute archive path {subject}")

    trimmed = name.removesuffix("/")
    _require(bool(trimmed), f"root-only archive path {subject}")
    _require(not trimmed.endswith("/"), f"repeated trailing slash in archive path {subject}")
    parts = tuple(trimmed.split("/"))
    _require(all(parts), f"empty component in archive path {subject}")
    _require(all(part not in {".", ".."} for part in parts), f"traversal in archive path {subject}")

    for part in parts:
        _require(part == unicodedata.normalize("NFC", part), f"non-NFC archive path {subject}")
        _require(not part.endswith((".", " ")), f"Windows-ambiguous archive path {subject}")
        _require(":" not in part, f"Windows drive/stream syntax in archive path {subject}")
        _require(not WINDOWS_DEVICE_RE.fullmatch(part), f"Windows device name in archive path {subject}")

    canonical = PurePosixPath(*parts).as_posix()
    _require(canonical == trimmed, f"non-canonical archive path {subject}")
    return parts


def _logical_digest(entries: Mapping[str, LogicalEntry]) -> str:
    payload = [
        {
            "kind": entry.kind,
            "mode": entry.mode,
            "path": path,
            "sha256": entry.sha256,
            "size": entry.size,
        }
        for path, entry in sorted(entries.items())
    ]
    encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    return hashlib.sha256(encoded).hexdigest()


def inspect_sdist(path: Path) -> LogicalSdist:
    path = path.resolve()
    _require(path.is_file(), f"sdist does not exist: {path}")
    _require(path.name.endswith(".tar.gz"), f"sdist must be a .tar.gz archive: {path.name}")

    entries: dict[str, LogicalEntry] = {}
    collision_keys: dict[str, str] = {}
    top_directory: str | None = None
    top_entry_seen = False

    with ExitStack() as stack:
        try:
            archive = stack.enter_context(tarfile.open(path, mode="r:gz"))
        except (OSError, tarfile.TarError) as exc:
            raise SdistIdentityError(f"cannot read sdist {path}: {exc}") from exc
        members = archive.getmembers()
        _require(bool(members), f"sdist is empty: {path.name}")
        for member in members:
            parts = _safe_components(member.name, source=path)
            _require(
                not member.name.endswith("/") or member.isdir(),
                f"non-directory archive entry has a trailing slash: {member.name}",
            )
            if top_directory is None:
                top_directory = parts[0]
            _require(
                parts[0] == top_directory,
                f"sdist must contain exactly one top-level directory: {path.name}",
            )

            if len(parts) == 1:
                _require(member.isdir(), f"top-level sdist entry must be a directory: {member.name}")
                _require(member.size == 0, f"directory has non-zero size: {member.name}")
                _require(not top_entry_seen, f"duplicate normalized path: {top_directory}")
                top_entry_seen = True
                continue

            logical_parts = parts[1:]
            logical_path = PurePosixPath(*logical_parts).as_posix()
            _require(
                logical_parts[0].casefold() not in FORBIDDEN_ROOT_KEYS,
                f"forbidden release marker/evidence payload in sdist: {logical_path}",
            )

            collision_key = "/".join(part.casefold() for part in logical_parts)
            previous = collision_keys.get(collision_key)
            _require(
                previous is None,
                f"duplicate/Windows-colliding normalized path: {previous!r} and {logical_path!r}",
            )
            collision_keys[collision_key] = logical_path

            _require(
                member.isfile() or member.isdir(),
                f"unsupported symlink/hardlink/device entry: {logical_path}",
            )
            mode = member.mode & 0o7777
            if member.isdir():
                _require(member.size == 0, f"directory has non-zero size: {logical_path}")
                entry = LogicalEntry(kind="directory", mode=mode, size=0, sha256=None)
            else:
                stream = archive.extractfile(member)
                _require(stream is not None, f"cannot read regular file: {logical_path}")
                content = stream.read()
                _require(
                    len(content) == member.size,
                    f"regular file size mismatch in archive: {logical_path}",
                )
                entry = LogicalEntry(
                    kind="file",
                    mode=mode,
                    size=member.size,
                    sha256=hashlib.sha256(content).hexdigest(),
                )
            _require(logical_path not in entries, f"duplicate normalized path: {logical_path}")
            entries[logical_path] = entry

    assert top_directory is not None
    _require(bool(entries), f"sdist has no logical payload after stripping top directory: {path.name}")
    return LogicalSdist(
        source=path,
        top_directory=top_directory,
        entries=entries,
        digest=_logical_digest(entries),
    )


def compare_sdists(candidate: Path, publication: Path) -> str:
    candidate_sdist = inspect_sdist(candidate)
    publication_sdist = inspect_sdist(publication)
    if candidate_sdist.entries != publication_sdist.entries:
        candidate_paths = set(candidate_sdist.entries)
        publication_paths = set(publication_sdist.entries)
        missing = sorted(candidate_paths - publication_paths)
        added = sorted(publication_paths - candidate_paths)
        changed = sorted(
            path
            for path in candidate_paths & publication_paths
            if candidate_sdist.entries[path] != publication_sdist.entries[path]
        )
        details: list[str] = []
        if missing:
            details.append(f"missing from publication: {missing!r}")
        if added:
            details.append(f"added in publication: {added!r}")
        if changed:
            details.append(f"changed in publication: {changed!r}")
        raise SdistIdentityError("logical sdist payload differs (" + "; ".join(details) + ")")
    _require(
        candidate_sdist.digest == publication_sdist.digest,
        "internal error: identical logical payloads produced different digests",
    )
    return candidate_sdist.digest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare candidate and publication SwirEngine 2.2 sdists logically.",
    )
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--publication", required=True, type=Path)
    parser.add_argument("--github-output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        digest = compare_sdists(args.candidate, args.publication)
        if args.github_output is not None:
            with args.github_output.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(f"logical_sdist_sha256={digest}\n")
    except (OSError, SdistIdentityError) as exc:
        print(f"Logical sdist verification FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"Logical sdist identity PASS: sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
