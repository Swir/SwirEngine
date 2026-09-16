from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from secrets import token_hex
from typing import Any


@dataclass(frozen=True, slots=True)
class DerivedAssetCacheDiagnostics:
    """Low-cost diagnostics for the persistent derived-asset cache."""

    entries: int
    bytes_used: int
    hits: int
    misses: int
    writes: int
    evictions: int


class DerivedAssetCache:
    """Content-addressed persistent cache for CPU-derived asset artifacts.

    Entries are addressed by a caller-controlled namespace and logical key, but file names are
    SHA-256 digests so arbitrary source paths never escape the cache root. Writes are transactional:
    bytes are written to a sibling temporary file, flushed to disk and atomically replaced into the
    final location. The cache stores bytes/JSON only; it deliberately avoids pickle or executable
    deserialization formats.
    """

    def __init__(
        self,
        root: str | Path,
        *,
        max_entries: int = 2048,
        max_bytes: int = 512 * 1024 * 1024,
    ) -> None:
        entries = int(max_entries)
        byte_budget = int(max_bytes)
        if entries <= 0:
            raise ValueError("max_entries must be greater than zero")
        if byte_budget <= 0:
            raise ValueError("max_bytes must be greater than zero")
        self.root = Path(root).expanduser().resolve()
        self.max_entries = entries
        self.max_bytes = byte_budget
        self.root.mkdir(parents=True, exist_ok=True)
        self._hits = 0
        self._misses = 0
        self._writes = 0
        self._evictions = 0

    @staticmethod
    def digest(namespace: str, key: str) -> str:
        namespace_value = str(namespace).strip()
        key_value = str(key)
        if not namespace_value:
            raise ValueError("cache namespace cannot be empty")
        if not key_value:
            raise ValueError("cache key cannot be empty")
        payload = f"{namespace_value}\0{key_value}".encode()
        return hashlib.sha256(payload).hexdigest()

    def path_for(self, namespace: str, key: str) -> Path:
        digest = self.digest(namespace, key)
        directory = self.root / digest[:2]
        return directory / f"{digest[2:]}.bin"

    def contains(self, namespace: str, key: str) -> bool:
        return self.path_for(namespace, key).is_file()

    def get_bytes(self, namespace: str, key: str) -> bytes | None:
        path = self.path_for(namespace, key)
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            self._misses += 1
            return None
        self._hits += 1
        try:
            os.utime(path, None)
        except FileNotFoundError:
            pass
        return data

    def put_bytes(self, namespace: str, key: str, data: bytes | bytearray | memoryview) -> Path:
        payload = bytes(data)
        if len(payload) > self.max_bytes:
            raise ValueError("artifact exceeds the configured cache byte budget")
        path = self.path_for(namespace, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{token_hex(8)}.tmp")
        try:
            with temporary.open("wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
        self._writes += 1
        self.prune()
        return path

    def get_json(self, namespace: str, key: str) -> Any | None:
        data = self.get_bytes(namespace, key)
        if data is None:
            return None
        return json.loads(data.decode("utf-8"))

    def put_json(self, namespace: str, key: str, value: Any) -> Path:
        data = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return self.put_bytes(namespace, key, data)

    def remove(self, namespace: str, key: str) -> bool:
        path = self.path_for(namespace, key)
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        self._remove_empty_parent(path.parent)
        return True

    def clear(self) -> int:
        removed = 0
        for path in self._entries():
            try:
                path.unlink()
            except FileNotFoundError:
                continue
            removed += 1
        for directory in sorted(self.root.iterdir(), reverse=True):
            if directory.is_dir():
                self._remove_empty_parent(directory)
        return removed

    def prune(self) -> int:
        entries = self._entry_records()
        count = len(entries)
        bytes_used = sum(size for _path, _mtime, size in entries)
        if count <= self.max_entries and bytes_used <= self.max_bytes:
            return 0
        removed = 0
        for path, _mtime, size in sorted(entries, key=lambda item: (item[1], str(item[0]))):
            if count <= self.max_entries and bytes_used <= self.max_bytes:
                break
            try:
                path.unlink()
            except FileNotFoundError:
                continue
            count -= 1
            bytes_used -= size
            removed += 1
            self._evictions += 1
            self._remove_empty_parent(path.parent)
        return removed

    @property
    def diagnostics(self) -> DerivedAssetCacheDiagnostics:
        records = self._entry_records()
        return DerivedAssetCacheDiagnostics(
            entries=len(records),
            bytes_used=sum(size for _path, _mtime, size in records),
            hits=self._hits,
            misses=self._misses,
            writes=self._writes,
            evictions=self._evictions,
        )

    def _entries(self) -> tuple[Path, ...]:
        if not self.root.is_dir():
            return ()
        return tuple(path for path in self.root.glob("*/*.bin") if path.is_file())

    def _entry_records(self) -> tuple[tuple[Path, int, int], ...]:
        records: list[tuple[Path, int, int]] = []
        for path in self._entries():
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue
            records.append((path, int(stat.st_mtime_ns), int(stat.st_size)))
        return tuple(records)

    def _remove_empty_parent(self, directory: Path) -> None:
        if directory == self.root:
            return
        try:
            directory.rmdir()
        except OSError:
            pass
