from __future__ import annotations

import hashlib
import json
import re
import stat
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType

from .diagnostics19 import RuntimeCrashReport, RuntimeDiagnosticsError

_EXPORT_FORMAT = "swirengine-export"
_EXPORT_VERSION = 2
_BUILD_SEAL_FORMAT = "swirengine-build-integrity"
_BUILD_SEAL_VERSION = 1
_BUNDLE_FORMAT = "swirengine.support-bundle"
_BUNDLE_VERSION = 1
_MANIFEST_NAME = "swir-export.json"
_SEAL_NAME = "swir-build-integrity.json"
_ALLOWED_SUPPORT_ENTRIES = frozenset({"bundle.json", "report.json"})
_MAX_JSON_BYTES = 2 * 1024 * 1024
_MAX_SUPPORT_ENTRY_BYTES = 1024 * 1024
_MAX_SUPPORT_TOTAL_BYTES = 2 * 1024 * 1024
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SENSITIVE_KEY = re.compile(
    r"(?:password|passwd|token|secret|authorization|cookie|credential|api[-_]?key|session[-_]?id)",
    re.IGNORECASE,
)
_UNREDACTED_SECRET_TEXT = re.compile(
    r"(?i)\b(password|passwd|token|secret|authorization|api[-_]?key)\b\s*[:=]\s*(?!<redacted>)([^\s,;]+)"
)


class ReleaseSafetyError(ValueError):
    """Raised when staged build or support-bundle integrity cannot be proven."""


def _canonical_json_bytes(value: Mapping[str, object]) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ReleaseSafetyError(f"release metadata is not portable JSON: {exc}") from exc


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ReleaseSafetyError(f"cannot read staged file: {path}") from exc
    return digest.hexdigest()


def _read_json_bytes(raw: bytes, *, label: str) -> dict[str, object]:
    if len(raw) > _MAX_JSON_BYTES:
        raise ReleaseSafetyError(f"{label} exceeds {_MAX_JSON_BYTES} bytes")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseSafetyError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ReleaseSafetyError(f"{label} root must be a JSON object")
    return value


def _read_json_file(path: Path, *, label: str) -> tuple[dict[str, object], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ReleaseSafetyError(f"cannot read {label}: {path}") from exc
    return _read_json_bytes(raw, label=label), raw


def _safe_relative(value: object, *, label: str) -> str:
    raw = str(value)
    if not raw or "\\" in raw or "\x00" in raw:
        raise ReleaseSafetyError(f"{label} must be a non-empty portable POSIX path")
    parts = raw.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ReleaseSafetyError(f"{label} contains an unsafe path component: {raw!r}")
    path = PurePosixPath(raw)
    if path.is_absolute():
        raise ReleaseSafetyError(f"{label} must be relative: {raw!r}")
    return path.as_posix()


def _unique_portable_paths(values: object, *, label: str) -> tuple[str, ...]:
    if not isinstance(values, list):
        raise ReleaseSafetyError(f"{label} must be a list")
    normalized = tuple(_safe_relative(value, label=label) for value in values)
    if len(normalized) != len(set(normalized)):
        raise ReleaseSafetyError(f"{label} contains duplicate paths")
    folded: dict[str, str] = {}
    for path in normalized:
        key = path.casefold()
        other = folded.setdefault(key, path)
        if other != path:
            raise ReleaseSafetyError(
                f"{label} contains a cross-platform case collision: {other!r} vs {path!r}"
            )
    return normalized


def _checksum_map(value: object, *, label: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ReleaseSafetyError(f"{label} must be a JSON object")
    result: dict[str, str] = {}
    folded: dict[str, str] = {}
    for raw_path, raw_digest in value.items():
        path = _safe_relative(raw_path, label=f"{label} path")
        digest = str(raw_digest).lower()
        if not _SHA256_RE.fullmatch(digest):
            raise ReleaseSafetyError(f"{label} contains an invalid SHA-256 for {path!r}")
        key = path.casefold()
        other = folded.setdefault(key, path)
        if other != path:
            raise ReleaseSafetyError(
                f"{label} contains a cross-platform case collision: {other!r} vs {path!r}"
            )
        if path in result:
            raise ReleaseSafetyError(f"{label} contains duplicate path {path!r}")
        result[path] = digest
    return dict(sorted(result.items()))


def _portable_manifest_identity(
    manifest: Mapping[str, object],
    *,
    manifest_sha256: str,
    generated_sha256: Mapping[str, str],
) -> dict[str, object]:
    return {
        "format": "swirengine.build-identity",
        "version": 1,
        "manifest_sha256": manifest_sha256,
        "target": str(manifest.get("target", "")),
        "experimental": bool(manifest.get("experimental", False)),
        "entrypoint": str(manifest.get("entrypoint", "")),
        "app_name": str(manifest.get("app_name", "")),
        "files": list(manifest.get("files", [])),
        "sha256": dict(manifest.get("sha256", {})),
        "native_build_command": list(manifest.get("native_build_command", [])),
        "native_spec": manifest.get("native_spec"),
        "metadata": dict(manifest.get("metadata", {})),
        "generated_sha256": dict(sorted(generated_sha256.items())),
    }


@dataclass(frozen=True, slots=True)
class ExportIntegrityResult:
    root: Path
    manifest: Path
    build_id: str
    manifest_sha256: str
    files: tuple[str, ...]
    checksums: Mapping[str, str]
    generated_sha256: Mapping[str, str]
    sealed: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "checksums", MappingProxyType(dict(self.checksums)))
        object.__setattr__(
            self,
            "generated_sha256",
            MappingProxyType(dict(self.generated_sha256)),
        )


def _staged_files(root: Path) -> set[str]:
    result: set[str] = set()
    try:
        iterator = root.rglob("*")
        for path in iterator:
            if path.is_symlink():
                raise ReleaseSafetyError(f"staged export contains a symlink: {path}")
            if path.is_file():
                result.add(path.relative_to(root).as_posix())
    except OSError as exc:
        raise ReleaseSafetyError(f"cannot enumerate staged export: {root}") from exc
    return result


def verify_export_staging(
    root: str | Path,
    *,
    expected_build_id: str | None = None,
    require_seal: bool = False,
    allow_native_outputs: bool = False,
) -> ExportIntegrityResult:
    """Verify a staged export and derive its deterministic build identity.

    The verifier treats the export manifest as an inventory contract, validates every staged checksum,
    rejects path ambiguity and unexpected files, and folds generated build-spec bytes into the build ID.
    Native build/work directories are only tolerated when the caller explicitly opts in.
    """

    export_root = Path(root).expanduser().resolve()
    if not export_root.is_dir():
        raise ReleaseSafetyError(f"staged export directory does not exist: {export_root}")
    manifest_path = export_root / _MANIFEST_NAME
    manifest, manifest_raw = _read_json_file(manifest_path, label="export manifest")
    if manifest.get("format") != _EXPORT_FORMAT or manifest.get("version") != _EXPORT_VERSION:
        raise ReleaseSafetyError("unsupported export manifest format/version")

    files = _unique_portable_paths(manifest.get("files"), label="export files")
    checksums = _checksum_map(manifest.get("sha256"), label="export checksums")
    if set(files) != set(checksums):
        missing_hashes = sorted(set(files) - set(checksums))
        extra_hashes = sorted(set(checksums) - set(files))
        raise ReleaseSafetyError(
            f"export manifest file/checksum sets differ: missing={missing_hashes}, extra={extra_hashes}"
        )

    for relative in files:
        path = export_root / relative
        if not path.is_file() or path.is_symlink():
            raise ReleaseSafetyError(f"required staged file is missing or unsafe: {relative}")
        actual = _sha256_file(path)
        if actual != checksums[relative]:
            raise ReleaseSafetyError(
                f"staged file checksum mismatch for {relative}: expected {checksums[relative]}, got {actual}"
            )

    generated_sha256: dict[str, str] = {}
    native_spec = manifest.get("native_spec")
    if native_spec is not None:
        spec_name = _safe_relative(native_spec, label="native spec")
        spec_path = export_root / spec_name
        if not spec_path.is_file() or spec_path.is_symlink():
            raise ReleaseSafetyError(f"declared native spec is missing or unsafe: {spec_name}")
        generated_sha256[spec_name] = _sha256_file(spec_path)

    expected_files = set(files) | {_MANIFEST_NAME} | set(generated_sha256)
    seal_path = export_root / _SEAL_NAME
    if seal_path.exists():
        expected_files.add(_SEAL_NAME)
    actual_files = _staged_files(export_root)
    extras = actual_files - expected_files
    if allow_native_outputs:
        extras = {
            value
            for value in extras
            if not value.startswith(("native-dist/", "native-build/"))
        }
    if extras:
        raise ReleaseSafetyError(f"staged export contains unexpected files: {sorted(extras)}")
    missing = expected_files - actual_files
    if missing:
        raise ReleaseSafetyError(f"staged export is missing expected files: {sorted(missing)}")

    manifest_sha256 = _sha256_bytes(manifest_raw)
    identity = _portable_manifest_identity(
        manifest,
        manifest_sha256=manifest_sha256,
        generated_sha256=generated_sha256,
    )
    build_id = _sha256_bytes(_canonical_json_bytes(identity))
    if expected_build_id is not None and build_id != expected_build_id:
        raise ReleaseSafetyError(
            f"build identity mismatch: expected {expected_build_id}, got {build_id}"
        )

    sealed = seal_path.is_file()
    if require_seal and not sealed:
        raise ReleaseSafetyError("staged export has no build-integrity seal")
    if sealed:
        seal, _ = _read_json_file(seal_path, label="build-integrity seal")
        if seal.get("format") != _BUILD_SEAL_FORMAT or seal.get("version") != _BUILD_SEAL_VERSION:
            raise ReleaseSafetyError("unsupported build-integrity seal format/version")
        if seal.get("build_id") != build_id:
            raise ReleaseSafetyError("build-integrity seal build_id does not match staged content")
        if seal.get("manifest_sha256") != manifest_sha256:
            raise ReleaseSafetyError("build-integrity seal manifest hash does not match")
        if seal.get("file_count") != len(files):
            raise ReleaseSafetyError("build-integrity seal file count does not match")
        sealed_generated = _checksum_map(
            seal.get("generated_sha256", {}),
            label="sealed generated checksums",
        )
        if sealed_generated != generated_sha256:
            raise ReleaseSafetyError("build-integrity seal generated checksums do not match")

    return ExportIntegrityResult(
        root=export_root,
        manifest=manifest_path,
        build_id=build_id,
        manifest_sha256=manifest_sha256,
        files=files,
        checksums=checksums,
        generated_sha256=generated_sha256,
        sealed=sealed,
    )


def seal_export_staging(root: str | Path) -> ExportIntegrityResult:
    """Verify and seal a staged export with its deterministic identity."""

    export_root = Path(root).expanduser().resolve()
    seal_path = export_root / _SEAL_NAME
    if seal_path.exists():
        seal_path.unlink()
    result = verify_export_staging(export_root)
    seal = {
        "format": _BUILD_SEAL_FORMAT,
        "version": _BUILD_SEAL_VERSION,
        "build_id": result.build_id,
        "manifest_sha256": result.manifest_sha256,
        "file_count": len(result.files),
        "generated_sha256": dict(result.generated_sha256),
    }
    encoded = json.dumps(
        seal,
        sort_keys=True,
        indent=2,
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8") + b"\n"
    temporary = seal_path.with_name(f".{seal_path.name}.tmp")
    try:
        temporary.write_bytes(encoded)
        temporary.replace(seal_path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return verify_export_staging(export_root, expected_build_id=result.build_id, require_seal=True)


@dataclass(frozen=True, slots=True)
class SupportBundleAudit:
    path: Path
    report_fingerprint: str
    report_sha256: str
    build_id: str
    entries: tuple[str, ...]


def _audit_sensitive_values(value: object, *, path: str = "report") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            name = str(key)
            if _SENSITIVE_KEY.search(name) and item != "<redacted>":
                raise ReleaseSafetyError(f"support report contains an unredacted sensitive field: {path}.{name}")
            _audit_sensitive_values(item, path=f"{path}.{name}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _audit_sensitive_values(item, path=f"{path}[{index}]")
    elif isinstance(value, str) and _UNREDACTED_SECRET_TEXT.search(value):
        raise ReleaseSafetyError(f"support report contains unredacted secret-like text at {path}")


def verify_support_bundle(
    path: str | Path,
    *,
    expected_build_id: str | None = None,
) -> SupportBundleAudit:
    """Audit an opt-in support ZIP for integrity, privacy boundaries and build identity."""

    bundle_path = Path(path).expanduser().resolve()
    try:
        archive = zipfile.ZipFile(bundle_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ReleaseSafetyError(f"support bundle is not a readable ZIP: {bundle_path}") from exc
    with archive:
        infos = archive.infolist()
        names = tuple(info.filename for info in infos)
        if len(names) != len(set(names)):
            raise ReleaseSafetyError("support bundle contains duplicate ZIP entries")
        if set(names) != _ALLOWED_SUPPORT_ENTRIES:
            raise ReleaseSafetyError(
                f"support bundle entries must be exactly {sorted(_ALLOWED_SUPPORT_ENTRIES)}"
            )
        total = 0
        payloads: dict[str, bytes] = {}
        for info in infos:
            name = _safe_relative(info.filename, label="support bundle entry")
            unix_mode = (info.external_attr >> 16) & 0o170000
            if info.is_dir() or unix_mode == stat.S_IFLNK or info.flag_bits & 0x1:
                raise ReleaseSafetyError(f"support bundle contains an unsafe ZIP entry: {name}")
            if info.file_size > _MAX_SUPPORT_ENTRY_BYTES:
                raise ReleaseSafetyError(f"support bundle entry is too large: {name}")
            total += info.file_size
            if total > _MAX_SUPPORT_TOTAL_BYTES:
                raise ReleaseSafetyError("support bundle uncompressed payload exceeds the safety limit")
            payloads[name] = archive.read(info)

    bundle = _read_json_bytes(payloads["bundle.json"], label="support bundle manifest")
    report_data = _read_json_bytes(payloads["report.json"], label="support report")
    if bundle.get("format") != _BUNDLE_FORMAT or bundle.get("format_version") != _BUNDLE_VERSION:
        raise ReleaseSafetyError("unsupported support bundle format/version")
    if bundle.get("report") != "report.json":
        raise ReleaseSafetyError("support bundle manifest points at an unexpected report entry")

    privacy = bundle.get("privacy")
    if not isinstance(privacy, Mapping):
        raise ReleaseSafetyError("support bundle privacy declaration is missing")
    required_false = (
        "automatic_environment_capture",
        "automatic_argv_capture",
        "automatic_user_file_capture",
        "trace_source_lines",
    )
    for key in required_false:
        if privacy.get(key) is not False:
            raise ReleaseSafetyError(f"support bundle privacy boundary is not locked: {key}")

    report_sha256 = _sha256_bytes(payloads["report.json"])
    if bundle.get("report_sha256") != report_sha256:
        raise ReleaseSafetyError("support bundle report SHA-256 does not match packaged bytes")
    _audit_sensitive_values(report_data)
    try:
        report = RuntimeCrashReport.from_dict(report_data)
    except RuntimeDiagnosticsError as exc:
        raise ReleaseSafetyError(f"support report contract is invalid: {exc}") from exc
    if bundle.get("report_fingerprint") != report.fingerprint:
        raise ReleaseSafetyError("support bundle report fingerprint does not match report content")
    for frame in report.trace:
        filename = frame.filename.replace("\\", "/")
        if filename.startswith("/") or ".." in PurePosixPath(filename).parts:
            raise ReleaseSafetyError("support report contains an unsafe trace path")

    build_id = report.identity.build_id
    if expected_build_id is not None and build_id != expected_build_id:
        raise ReleaseSafetyError(
            f"support report build identity mismatch: expected {expected_build_id}, got {build_id or '<empty>'}"
        )
    return SupportBundleAudit(
        path=bundle_path,
        report_fingerprint=report.fingerprint,
        report_sha256=report_sha256,
        build_id=build_id,
        entries=tuple(sorted(names)),
    )
