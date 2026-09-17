from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from secrets import token_hex

from ._content16_common import (
    ContentIntegrityError,
    ContentSafetyError,
    ContentStateError,
    _coerce_non_negative_int,
    _resolve_root,
    _safe_path,
    _sha256_bytes,
    _sha256_file,
)
from ._content16_manifest import ContentEntry


@dataclass(frozen=True, slots=True)
class CacheDiagnostics:
    verified_hits: int
    misses: int
    promotions: int
    rejected_promotions: int


class VerifiedContentCache:
    """Content-addressed cache that promotes only bytes matching a manifest entry."""

    def __init__(self, root: str | Path) -> None:
        self.root = _resolve_root(root, create=True)
        self._verified_hits = 0
        self._misses = 0
        self._promotions = 0
        self._rejected_promotions = 0

    def _object_path(self, entry: ContentEntry, *, create_parents: bool = False) -> Path:
        relative = f"objects/sha256/{entry.sha256[:2]}/{entry.sha256[2:]}"
        return _safe_path(self.root, relative, create_parents=create_parents)

    def path_for(self, entry: ContentEntry) -> Path:
        return self._object_path(entry)

    def verify(self, entry: ContentEntry) -> bool:
        path = self._object_path(entry)
        if path.is_symlink() or not path.is_file():
            self._misses += 1
            return False
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            self._misses += 1
            return False
        if size != entry.size or _sha256_file(path) != entry.sha256:
            self._misses += 1
            return False
        self._verified_hits += 1
        return True

    def put_bytes(self, entry: ContentEntry, data: bytes | bytearray | memoryview) -> Path:
        payload = bytes(data)
        if len(payload) != entry.size or _sha256_bytes(payload) != entry.sha256:
            self._rejected_promotions += 1
            raise ContentIntegrityError(f"bytes do not match manifest entry: {entry.path}")
        return self._write_verified(entry, payload)

    def put_file(self, entry: ContentEntry, source: str | Path) -> Path:
        source_path = Path(source)
        if source_path.is_symlink() or not source_path.is_file():
            self._rejected_promotions += 1
            raise ContentSafetyError("cache source must be a regular non-symlink file")
        if source_path.stat().st_size != entry.size or _sha256_file(source_path) != entry.sha256:
            self._rejected_promotions += 1
            raise ContentIntegrityError(f"file does not match manifest entry: {entry.path}")
        target = self._object_path(entry, create_parents=True)
        temporary = target.with_name(f".{target.name}.{token_hex(8)}.tmp")
        try:
            with source_path.open("rb") as source_handle, temporary.open("wb") as target_handle:
                shutil.copyfileobj(source_handle, target_handle, length=1024 * 1024)
                target_handle.flush()
                os.fsync(target_handle.fileno())
            if temporary.stat().st_size != entry.size or _sha256_file(temporary) != entry.sha256:
                self._rejected_promotions += 1
                raise ContentIntegrityError(
                    f"cache copy changed during verification: {entry.path}"
                )
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        self._promotions += 1
        return target

    def _write_verified(self, entry: ContentEntry, payload: bytes) -> Path:
        target = self._object_path(entry, create_parents=True)
        temporary = target.with_name(f".{target.name}.{token_hex(8)}.tmp")
        try:
            with temporary.open("wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        self._promotions += 1
        return target

    @property
    def diagnostics(self) -> CacheDiagnostics:
        return CacheDiagnostics(
            verified_hits=self._verified_hits,
            misses=self._misses,
            promotions=self._promotions,
            rejected_promotions=self._rejected_promotions,
        )


@dataclass(frozen=True, slots=True)
class StageProgress:
    path: str
    received_bytes: int
    expected_bytes: int

    @property
    def complete(self) -> bool:
        return self.received_bytes == self.expected_bytes


@dataclass(slots=True)
class ContentStager:
    """Local, resumable staging with explicit offsets and integrity-gated cache promotion."""

    root: Path
    chunks_written: int = 0
    bytes_written: int = 0
    resumes: int = 0
    integrity_failures: int = 0

    def __init__(self, root: str | Path) -> None:
        self.root = _resolve_root(root, create=True)
        self.chunks_written = 0
        self.bytes_written = 0
        self.resumes = 0
        self.integrity_failures = 0

    def _partial_path(self, entry: ContentEntry, *, create_parents: bool = False) -> Path:
        relative = f"partial/{entry.sha256[:2]}/{entry.sha256[2:]}.part"
        return _safe_path(self.root, relative, create_parents=create_parents)

    def partial_path(self, entry: ContentEntry) -> Path:
        return self._partial_path(entry)

    def progress(self, entry: ContentEntry) -> StageProgress:
        partial = self.partial_path(entry)
        if partial.is_symlink():
            raise ContentSafetyError("staging partial cannot be a symbolic link")
        try:
            received = partial.stat().st_size
        except FileNotFoundError:
            received = 0
        if received > entry.size:
            raise ContentStateError("staging partial exceeds the declared entry size")
        return StageProgress(entry.path, received, entry.size)

    def append(
        self,
        entry: ContentEntry,
        offset: int,
        data: bytes | bytearray | memoryview,
    ) -> StageProgress:
        expected_offset = _coerce_non_negative_int(offset, "offset")
        payload = bytes(data)
        state = self.progress(entry)
        if expected_offset != state.received_bytes:
            raise ContentStateError(
                f"staging offset mismatch for {entry.path}: "
                f"expected {state.received_bytes}, got {expected_offset}"
            )
        if state.received_bytes + len(payload) > entry.size:
            raise ContentStateError("staging chunk would exceed the declared entry size")
        partial = self._partial_path(entry, create_parents=True)
        if state.received_bytes:
            self.resumes += 1
        with partial.open("ab") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        self.chunks_written += 1
        self.bytes_written += len(payload)
        return self.progress(entry)

    def stage_local_file(
        self,
        entry: ContentEntry,
        source: str | Path,
        *,
        chunk_size: int = 1024 * 1024,
    ) -> StageProgress:
        size = _coerce_non_negative_int(chunk_size, "chunk_size")
        if size == 0:
            raise ValueError("chunk_size must be greater than zero")
        source_path = Path(source)
        if source_path.is_symlink() or not source_path.is_file():
            raise ContentSafetyError("staging source must be a regular non-symlink file")
        if source_path.stat().st_size != entry.size:
            raise ContentIntegrityError("local staging source size does not match the manifest")
        state = self.progress(entry)
        with source_path.open("rb") as handle:
            handle.seek(state.received_bytes)
            offset = state.received_bytes
            while offset < entry.size:
                chunk = handle.read(min(size, entry.size - offset))
                if not chunk:
                    raise ContentStateError("local staging source ended unexpectedly")
                state = self.append(entry, offset, chunk)
                offset = state.received_bytes
        return state

    def finalize(self, entry: ContentEntry, cache: VerifiedContentCache) -> Path:
        state = self.progress(entry)
        if not state.complete:
            raise ContentStateError("cannot finalize an incomplete staged entry")
        partial = self.partial_path(entry)
        if partial.stat().st_size != entry.size or _sha256_file(partial) != entry.sha256:
            self.integrity_failures += 1
            partial.unlink(missing_ok=True)
            raise ContentIntegrityError(f"staged content failed verification: {entry.path}")
        target = cache.put_file(entry, partial)
        partial.unlink(missing_ok=True)
        return target

    def reset(self, entry: ContentEntry) -> None:
        self.partial_path(entry).unlink(missing_ok=True)

    def portable_diagnostics(self) -> dict[str, int]:
        return {
            "chunks_written": self.chunks_written,
            "bytes_written": self.bytes_written,
            "resumes": self.resumes,
            "integrity_failures": self.integrity_failures,
        }
