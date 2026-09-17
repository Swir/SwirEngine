from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from ._content16_common import (
    ContentSafetyError,
    _canonical_json_bytes,
    _normalize_relative_path,
    _resolve_root,
    _safe_path,
    _sha256_bytes,
    _sha256_file,
    _coerce_non_negative_int,
    _validate_sha256,
    _validate_version,
)

_MANIFEST_SCHEMA = "swirengine.content-manifest"
_MANIFEST_VERSION = 1
_PATCH_SCHEMA = "swirengine.content-patch"
_PATCH_VERSION = 1


@dataclass(frozen=True, slots=True, order=True)
class ContentEntry:
    """One immutable file record in a deterministic content manifest."""

    path: str
    sha256: str
    size: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _normalize_relative_path(self.path))
        object.__setattr__(self, "sha256", _validate_sha256(self.sha256))
        object.__setattr__(self, "size", _coerce_non_negative_int(self.size, "size"))

    def portable(self) -> dict[str, Any]:
        return {"path": self.path, "sha256": self.sha256, "size": self.size}


@dataclass(frozen=True, slots=True)
class ContentManifest:
    """Versioned, canonical content identity used for verification and patch planning."""

    content_version: str
    entries: tuple[ContentEntry, ...]
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "content_version", _validate_version(self.content_version))
        entries = tuple(self.entries)
        if entries != tuple(sorted(entries, key=lambda entry: entry.path)):
            raise ValueError("manifest entries must be sorted by canonical path")
        paths = [entry.path for entry in entries]
        if len(paths) != len(set(paths)):
            raise ValueError("manifest cannot contain duplicate content paths")
        metadata = tuple(self.metadata)
        if metadata != tuple(sorted(metadata)):
            raise ValueError("manifest metadata must be sorted")
        seen_keys: set[str] = set()
        for key, value in metadata:
            if not isinstance(key, str) or not key or key != key.strip():
                raise ValueError("manifest metadata keys must be non-empty trimmed strings")
            if key in seen_keys:
                raise ValueError("manifest metadata keys must be unique")
            seen_keys.add(key)
            if not isinstance(value, str):
                raise TypeError("manifest metadata values must be strings")
        object.__setattr__(self, "entries", entries)
        object.__setattr__(self, "metadata", metadata)

    @classmethod
    def create(
        cls,
        content_version: str,
        entries: Iterable[ContentEntry],
        *,
        metadata: Mapping[str, str] | None = None,
    ) -> "ContentManifest":
        ordered_entries = tuple(sorted(tuple(entries), key=lambda entry: entry.path))
        ordered_metadata = tuple(sorted((key, value) for key, value in (metadata or {}).items()))
        return cls(content_version, ordered_entries, ordered_metadata)

    @classmethod
    def parse_json(cls, payload: str | bytes | bytearray) -> "ContentManifest":
        if isinstance(payload, (bytes, bytearray)):
            payload = bytes(payload).decode("utf-8")
        if not isinstance(payload, str):
            raise TypeError("manifest payload must be JSON text or UTF-8 bytes")
        data = json.loads(payload)
        if not isinstance(data, dict):
            raise ValueError("manifest JSON root must be an object")
        expected = {"schema", "schema_version", "content_version", "metadata", "entries"}
        if set(data) != expected:
            raise ValueError("manifest JSON fields do not match the supported schema")
        if data["schema"] != _MANIFEST_SCHEMA or data["schema_version"] != _MANIFEST_VERSION:
            raise ValueError("unsupported content manifest schema")
        if not isinstance(data["entries"], list):
            raise ValueError("manifest entries must be an array")
        entries: list[ContentEntry] = []
        for item in data["entries"]:
            if not isinstance(item, dict) or set(item) != {"path", "sha256", "size"}:
                raise ValueError("manifest entry does not match the supported schema")
            entries.append(ContentEntry(item["path"], item["sha256"], item["size"]))
        metadata = data["metadata"]
        if not isinstance(metadata, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in metadata.items()
        ):
            raise ValueError("manifest metadata must be a string-to-string object")
        return cls.create(data["content_version"], entries, metadata=metadata)

    def portable(self) -> dict[str, Any]:
        return {
            "schema": _MANIFEST_SCHEMA,
            "schema_version": _MANIFEST_VERSION,
            "content_version": self.content_version,
            "metadata": dict(self.metadata),
            "entries": [entry.portable() for entry in self.entries],
        }

    def to_json(self) -> str:
        return _canonical_json_bytes(self.portable()).decode("utf-8")

    @property
    def fingerprint(self) -> str:
        return _sha256_bytes(_canonical_json_bytes(self.portable()))

    @property
    def total_bytes(self) -> int:
        return sum(entry.size for entry in self.entries)

    def entry_map(self) -> dict[str, ContentEntry]:
        return {entry.path: entry for entry in self.entries}


def build_manifest(
    root: str | Path,
    content_version: str,
    *,
    metadata: Mapping[str, str] | None = None,
) -> ContentManifest:
    """Hash a local directory without following symbolic links."""

    base = _resolve_root(root)
    entries: list[ContentEntry] = []
    for directory, dir_names, file_names in os.walk(base, topdown=True, followlinks=False):
        directory_path = Path(directory)
        for name in tuple(dir_names):
            candidate = directory_path / name
            if candidate.is_symlink():
                raise ContentSafetyError(f"symbolic-link directory is not allowed: {candidate}")
        for name in file_names:
            candidate = directory_path / name
            if candidate.is_symlink():
                raise ContentSafetyError(f"symbolic-link file is not allowed: {candidate}")
            if not candidate.is_file():
                raise ContentSafetyError(f"non-regular file is not allowed: {candidate}")
            relative = candidate.relative_to(base).as_posix()
            stat = candidate.stat()
            entries.append(ContentEntry(relative, _sha256_file(candidate), int(stat.st_size)))
    return ContentManifest.create(content_version, entries, metadata=metadata)


@dataclass(frozen=True, slots=True)
class PatchPlan:
    """Deterministic manifest-to-manifest patch operations; it never executes content."""

    base_fingerprint: str
    target_fingerprint: str
    target_version: str
    additions: tuple[str, ...]
    replacements: tuple[str, ...]
    removals: tuple[str, ...]
    transfer_bytes: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_fingerprint", _validate_sha256(self.base_fingerprint))
        object.__setattr__(self, "target_fingerprint", _validate_sha256(self.target_fingerprint))
        object.__setattr__(
            self,
            "target_version",
            _validate_version(self.target_version, field_name="target_version"),
        )
        object.__setattr__(
            self,
            "transfer_bytes",
            _coerce_non_negative_int(self.transfer_bytes, "transfer_bytes"),
        )
        additions = tuple(self.additions)
        replacements = tuple(self.replacements)
        removals = tuple(self.removals)
        object.__setattr__(self, "additions", additions)
        object.__setattr__(self, "replacements", replacements)
        object.__setattr__(self, "removals", removals)
        groups = (additions, replacements, removals)
        for group in groups:
            if tuple(group) != tuple(sorted(group)):
                raise ValueError("patch paths must be sorted")
            for path in group:
                _normalize_relative_path(path)
        all_changed = (*self.additions, *self.replacements, *self.removals)
        if len(all_changed) != len(set(all_changed)):
            raise ValueError("a content path cannot appear in multiple patch operation groups")

    def portable(self) -> dict[str, Any]:
        return {
            "schema": _PATCH_SCHEMA,
            "schema_version": _PATCH_VERSION,
            "base_fingerprint": self.base_fingerprint,
            "target_fingerprint": self.target_fingerprint,
            "target_version": self.target_version,
            "additions": list(self.additions),
            "replacements": list(self.replacements),
            "removals": list(self.removals),
            "transfer_bytes": self.transfer_bytes,
        }

    @property
    def fingerprint(self) -> str:
        return _sha256_bytes(_canonical_json_bytes(self.portable()))

    @property
    def changed_files(self) -> int:
        return len(self.additions) + len(self.replacements) + len(self.removals)


def plan_patch(current: ContentManifest, target: ContentManifest) -> PatchPlan:
    current_entries = current.entry_map()
    target_entries = target.entry_map()
    additions = sorted(set(target_entries) - set(current_entries))
    removals = sorted(set(current_entries) - set(target_entries))
    replacements = sorted(
        path
        for path in set(current_entries) & set(target_entries)
        if current_entries[path] != target_entries[path]
    )
    transfer_bytes = sum(target_entries[path].size for path in (*additions, *replacements))
    return PatchPlan(
        base_fingerprint=current.fingerprint,
        target_fingerprint=target.fingerprint,
        target_version=target.content_version,
        additions=tuple(additions),
        replacements=tuple(replacements),
        removals=tuple(removals),
        transfer_bytes=transfer_bytes,
    )


@dataclass(frozen=True, slots=True)
class ContentIssue:
    path: str
    code: str
    expected: str | int | None = None
    actual: str | int | None = None


@dataclass(frozen=True, slots=True)
class VerificationReport:
    files_checked: int
    bytes_checked: int
    issues: tuple[ContentIssue, ...]

    @property
    def ok(self) -> bool:
        return not self.issues

    def portable(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "files_checked": self.files_checked,
            "bytes_checked": self.bytes_checked,
            "issues": [
                {
                    "path": issue.path,
                    "code": issue.code,
                    "expected": issue.expected,
                    "actual": issue.actual,
                }
                for issue in self.issues
            ],
        }


def verify_tree(
    root: str | Path,
    manifest: ContentManifest,
    *,
    reject_unexpected: bool = False,
) -> VerificationReport:
    base = _resolve_root(root)
    issues: list[ContentIssue] = []
    files_checked = 0
    bytes_checked = 0
    expected_paths = {entry.path for entry in manifest.entries}

    for entry in manifest.entries:
        try:
            path = _safe_path(base, entry.path)
        except ContentSafetyError:
            issues.append(ContentIssue(entry.path, "unsafe_path"))
            continue
        if not path.exists():
            issues.append(ContentIssue(entry.path, "missing"))
            continue
        if not path.is_file():
            issues.append(ContentIssue(entry.path, "not_regular_file"))
            continue
        size = path.stat().st_size
        files_checked += 1
        bytes_checked += size
        if size != entry.size:
            issues.append(ContentIssue(entry.path, "size_mismatch", entry.size, size))
            continue
        digest = _sha256_file(path)
        if digest != entry.sha256:
            issues.append(ContentIssue(entry.path, "hash_mismatch", entry.sha256, digest))

    if reject_unexpected:
        for directory, dir_names, file_names in os.walk(base, topdown=True, followlinks=False):
            directory_path = Path(directory)
            for name in tuple(dir_names):
                child = directory_path / name
                if child.is_symlink():
                    relative = child.relative_to(base).as_posix()
                    issues.append(ContentIssue(relative, "unsafe_symlink"))
                    dir_names.remove(name)
            for name in file_names:
                child = directory_path / name
                relative = child.relative_to(base).as_posix()
                if child.is_symlink():
                    issues.append(ContentIssue(relative, "unsafe_symlink"))
                elif relative not in expected_paths:
                    issues.append(ContentIssue(relative, "unexpected"))

    ordered_issues = tuple(sorted(issues, key=lambda item: (item.path, item.code)))
    return VerificationReport(files_checked, bytes_checked, ordered_issues)
