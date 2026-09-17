from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

_MANIFEST_SCHEMA = "swirengine.content-manifest"
_MANIFEST_VERSION = 1
_PATCH_SCHEMA = "swirengine.content-patch"
_PATCH_VERSION = 1
_SHA256_LENGTH = 64


class ContentError(RuntimeError):
    """Base error for the additive SwirEngine 1.6 content-delivery layer."""


class ContentSafetyError(ContentError):
    """Raised when a path or filesystem boundary would be unsafe to use."""


class ContentIntegrityError(ContentError):
    """Raised when bytes do not match their declared content identity."""


class ContentStateError(ContentError):
    """Raised when a resumable staging operation has an invalid state."""


def _validate_version(value: str, *, field_name: str = "content_version") -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value or value != value.strip():
        raise ValueError(f"{field_name} must be a non-empty trimmed string")
    if any(ord(character) < 32 for character in value):
        raise ValueError(f"{field_name} cannot contain control characters")
    return value


def _normalize_relative_path(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("content path must be a string")
    if not value or value.startswith("/") or value.endswith("/"):
        raise ValueError("content path must be a non-empty relative POSIX path")
    if "\\" in value or "\x00" in value or ":" in value:
        raise ValueError("content path is not portable")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("content path cannot contain empty, '.' or '..' segments")
    if any(any(ord(character) < 32 for character in part) for part in parts):
        raise ValueError("content path cannot contain control characters")
    return "/".join(parts)


def _validate_sha256(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("sha256 must be a string")
    digest = value.lower()
    if len(digest) != _SHA256_LENGTH or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise ValueError("sha256 must be a 64-character hexadecimal digest")
    return digest


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _coerce_non_negative_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} cannot be negative")
    return value


def _resolve_root(root: str | Path, *, create: bool = False) -> Path:
    path = Path(root).expanduser()
    if path.is_symlink():
        raise ContentSafetyError("content root cannot be a symbolic link")
    if create:
        path.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        raise FileNotFoundError(path)
    if not path.is_dir():
        raise NotADirectoryError(path)
    return path.resolve()


def _safe_path(root: Path, relative: str, *, create_parents: bool = False) -> Path:
    normalized = _normalize_relative_path(relative)
    current = root
    parts = normalized.split("/")
    for part in parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise ContentSafetyError(f"symbolic-link parent is not allowed: {normalized}")
        if current.exists():
            if not current.is_dir():
                raise ContentSafetyError(f"non-directory parent blocks content path: {normalized}")
        elif create_parents:
            current.mkdir()
        else:
            break
    target = root.joinpath(*parts)
    if target.is_symlink():
        raise ContentSafetyError(f"symbolic-link content path is not allowed: {normalized}")
    return target
