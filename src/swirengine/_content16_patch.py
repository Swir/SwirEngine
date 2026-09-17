from __future__ import annotations

import os
import shutil
from pathlib import Path
from secrets import token_hex

from ._content16_cache import VerifiedContentCache
from ._content16_common import (
    ContentIntegrityError,
    ContentSafetyError,
    ContentStateError,
    _normalize_relative_path,
    _resolve_root,
    _safe_path,
    _sha256_file,
)
from ._content16_manifest import ContentManifest, PatchPlan, VerificationReport, verify_tree


def _preflight_target_path(root: Path, relative: str) -> Path:
    path = _safe_path(root, relative, create_parents=False)
    parent = root
    for part in _normalize_relative_path(relative).split("/")[:-1]:
        parent = parent / part
        if parent.is_symlink():
            raise ContentSafetyError(f"target parent is a symbolic link: {relative}")
        if parent.exists() and not parent.is_dir():
            raise ContentSafetyError(f"target parent is not a directory: {relative}")
    if path.exists() and not path.is_file():
        raise ContentSafetyError(f"target path is not a regular file: {relative}")
    return path


def apply_patch(
    plan: PatchPlan,
    current_manifest: ContentManifest,
    target_manifest: ContentManifest,
    cache: VerifiedContentCache,
    target_root: str | Path,
) -> VerificationReport:
    """Materialize a verified patch from the exact verified base without executing content."""

    if plan.base_fingerprint != current_manifest.fingerprint:
        raise ContentStateError("patch base fingerprint does not match the current manifest")
    if plan.target_fingerprint != target_manifest.fingerprint:
        raise ContentStateError("patch target fingerprint does not match the target manifest")
    if plan.target_version != target_manifest.content_version:
        raise ContentStateError("patch target version does not match the target manifest")
    base = _resolve_root(target_root, create=True)
    base_report = verify_tree(base, current_manifest, reject_unexpected=True)
    if not base_report.ok:
        if any(issue.code == "unsafe_symlink" for issue in base_report.issues):
            raise ContentSafetyError("installed content contains an unsafe symbolic-link path")
        raise ContentStateError("installed content does not match the patch base manifest")

    target_entries = target_manifest.entry_map()
    transfer_paths = (*plan.additions, *plan.replacements)
    for path in transfer_paths:
        entry = target_entries.get(path)
        if entry is None:
            raise ContentStateError(f"patch transfer path is absent from target manifest: {path}")
        if not cache.verify(entry):
            raise ContentIntegrityError(f"verified cache object is unavailable: {path}")

    for path in (*transfer_paths, *plan.removals):
        _preflight_target_path(base, path)

    for relative in transfer_paths:
        entry = target_entries[relative]
        source = cache.path_for(entry)
        destination = _safe_path(base, relative, create_parents=True)
        temporary = destination.with_name(f".{destination.name}.{token_hex(8)}.tmp")
        try:
            with source.open("rb") as source_handle, temporary.open("wb") as target_handle:
                shutil.copyfileobj(source_handle, target_handle, length=1024 * 1024)
                target_handle.flush()
                os.fsync(target_handle.fileno())
            if temporary.stat().st_size != entry.size or _sha256_file(temporary) != entry.sha256:
                raise ContentIntegrityError(f"materialized content failed verification: {relative}")
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    for relative in plan.removals:
        destination = _safe_path(base, relative)
        if destination.exists():
            destination.unlink()

    return verify_tree(base, target_manifest, reject_unexpected=True)
