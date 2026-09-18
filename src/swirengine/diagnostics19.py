from __future__ import annotations

import hashlib
import json
import math
import os
import re
import traceback
import zipfile
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

_REPORT_FORMAT = "swirengine.runtime-report"
_BUNDLE_FORMAT = "swirengine.support-bundle"
_FORMAT_VERSION = 1
_MAX_REPORT_BYTES = 512 * 1024
_MAX_BUNDLE_REPORT_BYTES = 768 * 1024
_MAX_LOG_ENTRIES = 256
_MAX_LOG_MESSAGE = 2048
_MAX_CONTEXT_FIELDS = 32
_MAX_CONTEXT_VALUE = 1024
_MAX_DIAGNOSTIC_FIELDS = 64
_MAX_DIAGNOSTIC_DEPTH = 4
_MAX_SEQUENCE_ITEMS = 64
_MAX_TRACE_FRAMES = 64
_MAX_NAME = 128
_SENSITIVE_KEY = re.compile(
    r"(?:password|passwd|token|secret|authorization|cookie|credential|api[-_]?key|session[-_]?id)",
    re.IGNORECASE,
)
_SECRET_TEXT = re.compile(
    r"(?i)\b(password|passwd|token|secret|authorization|api[-_]?key)\b\s*[:=]\s*([^\s,;]+)"
)
_LOG_LEVELS = frozenset({"debug", "info", "warning", "error", "critical"})


class RuntimeDiagnosticsError(ValueError):
    """Raised when a 1.9 runtime diagnostic/report contract is malformed or unsafe."""


def _bounded_text(value: object, *, label: str, maximum: int) -> str:
    text = str(value)
    if "\x00" in text:
        raise RuntimeDiagnosticsError(f"{label} must not contain NUL characters")
    if len(text) > maximum:
        text = text[: maximum - 1] + "…"
    return text


def _name(value: object, *, label: str) -> str:
    text = _bounded_text(value, label=label, maximum=_MAX_NAME).strip()
    if not text:
        raise RuntimeDiagnosticsError(f"{label} must not be empty")
    return text


def _scrub_text(value: object, *, roots: Sequence[Path] = ()) -> str:
    text = _bounded_text(value, label="diagnostic text", maximum=_MAX_LOG_MESSAGE)
    for root in roots:
        try:
            raw = str(root.expanduser().resolve())
        except (OSError, RuntimeError):
            raw = str(root)
        if raw:
            text = text.replace(raw, "<project>")
            text = text.replace(raw.replace("\\", "/"), "<project>")
            text = text.replace(raw.replace("/", "\\"), "<project>")
    try:
        home = str(Path.home())
    except RuntimeError:  # pragma: no cover - defensive platform fallback
        home = ""
    if home:
        text = text.replace(home, "<home>")
        text = text.replace(home.replace("\\", "/"), "<home>")
        text = text.replace(home.replace("/", "\\"), "<home>")
    return _SECRET_TEXT.sub(lambda match: f"{match.group(1)}=<redacted>", text)


def _safe_scalar(value: object, *, roots: Sequence[Path] = ()) -> object:
    if value is None or isinstance(value, bool) or isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise RuntimeDiagnosticsError("diagnostic numeric values must be finite")
        return value
    return _scrub_text(value, roots=roots)[:_MAX_CONTEXT_VALUE]


def _safe_mapping(
    value: Mapping[str, object] | None,
    *,
    roots: Sequence[Path] = (),
    depth: int = 0,
) -> dict[str, object]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise RuntimeDiagnosticsError("diagnostic snapshot must be a mapping")
    if depth >= _MAX_DIAGNOSTIC_DEPTH:
        raise RuntimeDiagnosticsError(
            f"diagnostic snapshot nesting exceeds {_MAX_DIAGNOSTIC_DEPTH} levels"
        )
    if len(value) > _MAX_DIAGNOSTIC_FIELDS:
        raise RuntimeDiagnosticsError(
            f"diagnostic mappings support at most {_MAX_DIAGNOSTIC_FIELDS} fields"
        )
    result: dict[str, object] = {}
    for raw_key, raw_value in sorted(value.items(), key=lambda item: str(item[0]).casefold()):
        key = _name(raw_key, label="diagnostic field")
        if _SENSITIVE_KEY.search(key):
            result[key] = "<redacted>"
            continue
        if isinstance(raw_value, Mapping):
            result[key] = _safe_mapping(raw_value, roots=roots, depth=depth + 1)
        elif isinstance(raw_value, Sequence) and not isinstance(raw_value, (str, bytes, bytearray)):
            if len(raw_value) > _MAX_SEQUENCE_ITEMS:
                raise RuntimeDiagnosticsError(
                    f"diagnostic sequences support at most {_MAX_SEQUENCE_ITEMS} items"
                )
            normalized: list[object] = []
            for item in raw_value:
                if isinstance(item, Mapping):
                    normalized.append(_safe_mapping(item, roots=roots, depth=depth + 1))
                elif isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)):
                    raise RuntimeDiagnosticsError("nested diagnostic sequences are not supported")
                else:
                    normalized.append(_safe_scalar(item, roots=roots))
            result[key] = normalized
        else:
            result[key] = _safe_scalar(raw_value, roots=roots)
    return result


def _portable_json(value: Mapping[str, object], *, indent: int | None = None) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":") if indent is None else None,
            indent=indent,
        )
    except (TypeError, ValueError) as exc:
        raise RuntimeDiagnosticsError(f"diagnostic payload is not portable JSON: {exc}") from exc


def _fingerprint(value: Mapping[str, object]) -> str:
    return hashlib.sha256(_portable_json(value).encode("utf-8")).hexdigest()


def _atomic_write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return path


@dataclass(frozen=True, slots=True)
class RuntimeIdentity:
    """Non-secret identifiers that make a runtime report actionable for a creator."""

    engine_version: str
    project_name: str
    project_fingerprint: str
    build_id: str = ""
    profile: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "engine_version", _name(self.engine_version, label="engine version"))
        object.__setattr__(self, "project_name", _name(self.project_name, label="project name"))
        fingerprint = _name(self.project_fingerprint, label="project fingerprint")
        if len(fingerprint) > 128:
            raise RuntimeDiagnosticsError("project fingerprint must be at most 128 characters")
        object.__setattr__(self, "project_fingerprint", fingerprint)
        object.__setattr__(
            self,
            "build_id",
            _bounded_text(self.build_id, label="build id", maximum=128).strip(),
        )
        object.__setattr__(
            self,
            "profile",
            _bounded_text(self.profile, label="profile", maximum=64).strip(),
        )

    def portable(self) -> dict[str, str]:
        return {
            "engine_version": self.engine_version,
            "project_name": self.project_name,
            "project_fingerprint": self.project_fingerprint,
            "build_id": self.build_id,
            "profile": self.profile,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> RuntimeIdentity:
        try:
            return cls(
                engine_version=str(data["engine_version"]),
                project_name=str(data["project_name"]),
                project_fingerprint=str(data["project_fingerprint"]),
                build_id=str(data.get("build_id", "")),
                profile=str(data.get("profile", "")),
            )
        except KeyError as exc:
            raise RuntimeDiagnosticsError(f"runtime identity is missing {exc.args[0]!r}") from exc


def identity_from_project(
    project: object,
    *,
    engine_version: str,
    build_id: str = "",
    profile: str = "",
) -> RuntimeIdentity:
    """Create a report identity from a ProjectManifest-like object without reading extra files."""

    try:
        project_name = getattr(project, "name")
        project_fingerprint = getattr(project, "fingerprint")
    except Exception as exc:  # pragma: no cover - defensive for third-party manifest adapters
        raise RuntimeDiagnosticsError("project does not expose name/fingerprint") from exc
    return RuntimeIdentity(
        engine_version=engine_version,
        project_name=str(project_name),
        project_fingerprint=str(project_fingerprint),
        build_id=build_id,
        profile=profile,
    )


@dataclass(frozen=True, slots=True)
class RuntimeLogEntry:
    sequence: int
    level: str
    message: str
    fields: Mapping[str, object]

    def __post_init__(self) -> None:
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 0:
            raise RuntimeDiagnosticsError("log sequence must be a non-negative integer")
        level = str(self.level).strip().lower()
        if level not in _LOG_LEVELS:
            raise RuntimeDiagnosticsError(
                "log level must be one of: " + ", ".join(sorted(_LOG_LEVELS))
            )
        object.__setattr__(self, "level", level)
        object.__setattr__(
            self,
            "message",
            _bounded_text(self.message, label="log message", maximum=_MAX_LOG_MESSAGE),
        )
        normalized = _safe_mapping(self.fields)
        if len(normalized) > _MAX_CONTEXT_FIELDS:
            raise RuntimeDiagnosticsError(
                f"log fields support at most {_MAX_CONTEXT_FIELDS} values"
            )
        object.__setattr__(self, "fields", MappingProxyType(normalized))

    def portable(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "level": self.level,
            "message": self.message,
            "fields": dict(self.fields),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> RuntimeLogEntry:
        fields = data.get("fields", {})
        if not isinstance(fields, Mapping):
            raise RuntimeDiagnosticsError("runtime log fields must be a mapping")
        try:
            return cls(
                sequence=int(data["sequence"]),
                level=str(data["level"]),
                message=str(data["message"]),
                fields=fields,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeDiagnosticsError("invalid runtime log entry") from exc


class RuntimeLogBuffer:
    """Explicit bounded structured logs; no environment, argv or filesystem capture is automatic."""

    def __init__(self, *, capacity: int = _MAX_LOG_ENTRIES) -> None:
        if isinstance(capacity, bool) or not isinstance(capacity, int):
            raise TypeError("runtime log capacity must be an integer")
        if not 1 <= capacity <= _MAX_LOG_ENTRIES:
            raise ValueError(f"runtime log capacity must be between 1 and {_MAX_LOG_ENTRIES}")
        self._entries: deque[RuntimeLogEntry] = deque(maxlen=capacity)
        self._next_sequence = 0

    @property
    def entries(self) -> tuple[RuntimeLogEntry, ...]:
        return tuple(self._entries)

    def record(self, level: str, message: object, **fields: object) -> RuntimeLogEntry:
        if len(fields) > _MAX_CONTEXT_FIELDS:
            raise RuntimeDiagnosticsError(
                f"log fields support at most {_MAX_CONTEXT_FIELDS} values"
            )
        safe_fields = {
            key: ("<redacted>" if _SENSITIVE_KEY.search(key) else _safe_scalar(value))
            for key, value in fields.items()
        }
        entry = RuntimeLogEntry(
            sequence=self._next_sequence,
            level=level,
            message=_scrub_text(message),
            fields=safe_fields,
        )
        self._next_sequence += 1
        self._entries.append(entry)
        return entry

    def clear(self) -> None:
        self._entries.clear()


@dataclass(frozen=True, slots=True)
class RuntimeTraceFrame:
    filename: str
    function: str
    line: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "filename",
            _bounded_text(self.filename, label="trace filename", maximum=256),
        )
        object.__setattr__(self, "function", _name(self.function, label="trace function"))
        if isinstance(self.line, bool) or not isinstance(self.line, int) or self.line < 0:
            raise RuntimeDiagnosticsError("trace line must be a non-negative integer")

    def portable(self) -> dict[str, object]:
        return {"filename": self.filename, "function": self.function, "line": self.line}

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> RuntimeTraceFrame:
        try:
            return cls(
                filename=str(data["filename"]),
                function=str(data["function"]),
                line=int(data["line"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeDiagnosticsError("invalid runtime trace frame") from exc


def _trace_filename(filename: str, *, project_root: Path | None) -> str:
    path = Path(filename)
    if project_root is not None:
        try:
            return path.resolve().relative_to(project_root.resolve()).as_posix()
        except (OSError, RuntimeError, ValueError):
            pass
    return f"<external>/{path.name}" if path.name else "<external>"


def _trace_frames(exc: BaseException, *, project_root: Path | None) -> tuple[RuntimeTraceFrame, ...]:
    extracted = traceback.extract_tb(exc.__traceback__)[-_MAX_TRACE_FRAMES:]
    return tuple(
        RuntimeTraceFrame(
            filename=_trace_filename(item.filename, project_root=project_root),
            function=item.name or "<unknown>",
            line=max(0, int(item.lineno or 0)),
        )
        for item in extracted
    )


@dataclass(frozen=True, slots=True)
class RuntimeDiagnosticSnapshot:
    logs: tuple[RuntimeLogEntry, ...] = ()
    diagnostics: Mapping[str, object] | None = None
    performance: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        logs = tuple(self.logs)
        if len(logs) > _MAX_LOG_ENTRIES:
            raise RuntimeDiagnosticsError(
                f"runtime snapshots support at most {_MAX_LOG_ENTRIES} log entries"
            )
        if not all(isinstance(item, RuntimeLogEntry) for item in logs):
            raise RuntimeDiagnosticsError("runtime snapshot logs must contain RuntimeLogEntry values")
        object.__setattr__(self, "logs", logs)
        object.__setattr__(
            self,
            "diagnostics",
            MappingProxyType(_safe_mapping(self.diagnostics)),
        )
        object.__setattr__(
            self,
            "performance",
            MappingProxyType(_safe_mapping(self.performance)),
        )

    def portable(self) -> dict[str, object]:
        return {
            "logs": [entry.portable() for entry in self.logs],
            "diagnostics": dict(self.diagnostics or {}),
            "performance": dict(self.performance or {}),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> RuntimeDiagnosticSnapshot:
        raw_logs = data.get("logs", [])
        if not isinstance(raw_logs, list) or len(raw_logs) > _MAX_LOG_ENTRIES:
            raise RuntimeDiagnosticsError("runtime report logs are malformed or over the limit")
        logs: list[RuntimeLogEntry] = []
        for item in raw_logs:
            if not isinstance(item, Mapping):
                raise RuntimeDiagnosticsError("runtime report log entries must be mappings")
            logs.append(RuntimeLogEntry.from_dict(item))
        diagnostics = data.get("diagnostics", {})
        performance = data.get("performance", {})
        if not isinstance(diagnostics, Mapping) or not isinstance(performance, Mapping):
            raise RuntimeDiagnosticsError("runtime report snapshots must be mappings")
        return cls(tuple(logs), diagnostics, performance)


@dataclass(frozen=True, slots=True)
class RuntimeCrashReport:
    identity: RuntimeIdentity
    exception_type: str
    exception_message: str
    trace: tuple[RuntimeTraceFrame, ...]
    snapshot: RuntimeDiagnosticSnapshot
    format_version: int = _FORMAT_VERSION

    def __post_init__(self) -> None:
        if self.format_version != _FORMAT_VERSION:
            raise RuntimeDiagnosticsError("unsupported runtime report format version")
        if not isinstance(self.identity, RuntimeIdentity):
            raise RuntimeDiagnosticsError("runtime report identity is invalid")
        object.__setattr__(self, "exception_type", _name(self.exception_type, label="exception type"))
        object.__setattr__(
            self,
            "exception_message",
            _bounded_text(
                self.exception_message,
                label="exception message",
                maximum=_MAX_LOG_MESSAGE,
            ),
        )
        trace = tuple(self.trace)
        if len(trace) > _MAX_TRACE_FRAMES or not all(
            isinstance(item, RuntimeTraceFrame) for item in trace
        ):
            raise RuntimeDiagnosticsError("runtime report trace is invalid or over the limit")
        object.__setattr__(self, "trace", trace)
        if not isinstance(self.snapshot, RuntimeDiagnosticSnapshot):
            raise RuntimeDiagnosticsError("runtime report snapshot is invalid")

    def portable(self) -> dict[str, object]:
        return {
            "format": _REPORT_FORMAT,
            "format_version": self.format_version,
            "identity": self.identity.portable(),
            "exception": {
                "type": self.exception_type,
                "message": self.exception_message,
                "trace": [frame.portable() for frame in self.trace],
            },
            "snapshot": self.snapshot.portable(),
        }

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self.portable())

    def to_json(self, *, indent: int | None = 2) -> str:
        text = _portable_json(self.portable(), indent=indent)
        if len(text.encode("utf-8")) > _MAX_REPORT_BYTES:
            raise RuntimeDiagnosticsError(f"runtime report exceeds {_MAX_REPORT_BYTES} bytes")
        return text

    def export_json(self, path: str | Path) -> Path:
        payload = (self.to_json(indent=2) + "\n").encode("utf-8")
        return _atomic_write(Path(path), payload)

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> RuntimeCrashReport:
        if data.get("format") != _REPORT_FORMAT:
            raise RuntimeDiagnosticsError("unsupported runtime report format")
        if data.get("format_version") != _FORMAT_VERSION:
            raise RuntimeDiagnosticsError("unsupported runtime report format version")
        identity = data.get("identity")
        exception = data.get("exception")
        snapshot = data.get("snapshot")
        if not isinstance(identity, Mapping):
            raise RuntimeDiagnosticsError("runtime report identity must be a mapping")
        if not isinstance(exception, Mapping):
            raise RuntimeDiagnosticsError("runtime report exception must be a mapping")
        if not isinstance(snapshot, Mapping):
            raise RuntimeDiagnosticsError("runtime report snapshot must be a mapping")
        raw_trace = exception.get("trace", [])
        if not isinstance(raw_trace, list) or len(raw_trace) > _MAX_TRACE_FRAMES:
            raise RuntimeDiagnosticsError("runtime report trace is malformed or over the limit")
        frames: list[RuntimeTraceFrame] = []
        for item in raw_trace:
            if not isinstance(item, Mapping):
                raise RuntimeDiagnosticsError("runtime report trace entries must be mappings")
            frames.append(RuntimeTraceFrame.from_dict(item))
        try:
            exception_type = str(exception["type"])
            exception_message = str(exception.get("message", ""))
        except KeyError as exc:
            raise RuntimeDiagnosticsError("runtime report exception type is missing") from exc
        return cls(
            identity=RuntimeIdentity.from_dict(identity),
            exception_type=exception_type,
            exception_message=exception_message,
            trace=tuple(frames),
            snapshot=RuntimeDiagnosticSnapshot.from_dict(snapshot),
        )

    @classmethod
    def load_json(cls, path: str | Path) -> RuntimeCrashReport:
        source = Path(path)
        try:
            raw = source.read_bytes()
        except OSError as exc:
            raise RuntimeDiagnosticsError(f"cannot read runtime report: {source}") from exc
        if len(raw) > _MAX_REPORT_BYTES:
            raise RuntimeDiagnosticsError(f"runtime report exceeds {_MAX_REPORT_BYTES} bytes")
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeDiagnosticsError("runtime report is not valid UTF-8 JSON") from exc
        if not isinstance(data, Mapping):
            raise RuntimeDiagnosticsError("runtime report root must be a JSON object")
        return cls.from_dict(data)


def _portable_diagnostics(value: object, *, roots: Sequence[Path] = ()) -> dict[str, object]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return _safe_mapping(value, roots=roots)
    portable = getattr(value, "portable", None)
    if callable(portable):
        result = portable()
        if not isinstance(result, Mapping):
            raise RuntimeDiagnosticsError("diagnostics portable() must return a mapping")
        return _safe_mapping(result, roots=roots)
    capture = getattr(value, "capture", None)
    if callable(capture):
        result = capture()
        portable = getattr(result, "portable", None)
        if not callable(portable):
            raise RuntimeDiagnosticsError("diagnostics capture() must return a portable object")
        mapping = portable()
        if not isinstance(mapping, Mapping):
            raise RuntimeDiagnosticsError("diagnostics capture portable() must return a mapping")
        return _safe_mapping(mapping, roots=roots)
    raise RuntimeDiagnosticsError("diagnostics must be a mapping or expose portable()/capture()")


def capture_exception(
    exc: BaseException,
    *,
    identity: RuntimeIdentity,
    logs: RuntimeLogBuffer | Sequence[RuntimeLogEntry] | None = None,
    diagnostics: object = None,
    performance: object = None,
    project_root: str | Path | None = None,
) -> RuntimeCrashReport:
    """Capture a bounded opt-in report without locals, argv, environment or arbitrary files."""

    if not isinstance(exc, BaseException):
        raise TypeError("capture_exception requires a BaseException")
    root = Path(project_root).resolve() if project_root is not None else None
    roots = () if root is None else (root,)
    if logs is None:
        log_entries: tuple[RuntimeLogEntry, ...] = ()
    elif isinstance(logs, RuntimeLogBuffer):
        log_entries = logs.entries
    else:
        log_entries = tuple(logs)
    if len(log_entries) > _MAX_LOG_ENTRIES:
        log_entries = log_entries[-_MAX_LOG_ENTRIES:]
    snapshot = RuntimeDiagnosticSnapshot(
        logs=log_entries,
        diagnostics=_portable_diagnostics(diagnostics, roots=roots),
        performance=_portable_diagnostics(performance, roots=roots),
    )
    return RuntimeCrashReport(
        identity=identity,
        exception_type=f"{type(exc).__module__}.{type(exc).__qualname__}",
        exception_message=_scrub_text(str(exc), roots=roots),
        trace=_trace_frames(exc, project_root=root),
        snapshot=snapshot,
    )


@dataclass(frozen=True, slots=True)
class SupportBundleResult:
    path: Path
    report_fingerprint: str
    report_sha256: str
    entries: tuple[str, ...]


class SupportBundleBuilder:
    """Create a deterministic-entry support ZIP containing generated diagnostics only."""

    def __init__(self, report: RuntimeCrashReport) -> None:
        if not isinstance(report, RuntimeCrashReport):
            raise TypeError("support bundles require a RuntimeCrashReport")
        self.report = report

    def _entries(self) -> dict[str, bytes]:
        report_bytes = (self.report.to_json(indent=2) + "\n").encode("utf-8")
        if len(report_bytes) > _MAX_BUNDLE_REPORT_BYTES:
            raise RuntimeDiagnosticsError("runtime report is too large for a support bundle")
        digest = hashlib.sha256(report_bytes).hexdigest()
        manifest = {
            "format": _BUNDLE_FORMAT,
            "format_version": _FORMAT_VERSION,
            "report": "report.json",
            "report_fingerprint": self.report.fingerprint,
            "report_sha256": digest,
            "privacy": {
                "automatic_environment_capture": False,
                "automatic_argv_capture": False,
                "automatic_user_file_capture": False,
                "trace_source_lines": False,
            },
        }
        return {
            "bundle.json": (_portable_json(manifest, indent=2) + "\n").encode("utf-8"),
            "report.json": report_bytes,
        }

    def write(self, path: str | Path) -> SupportBundleResult:
        destination = Path(path)
        if destination.suffix.lower() != ".zip":
            raise RuntimeDiagnosticsError("support bundle output must use a .zip extension")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
        entries = self._entries()
        try:
            with zipfile.ZipFile(
                temporary,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            ) as archive:
                for name, payload in sorted(entries.items()):
                    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o600 << 16
                    archive.writestr(info, payload)
            os.replace(temporary, destination)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
        report_payload = entries["report.json"]
        return SupportBundleResult(
            path=destination,
            report_fingerprint=self.report.fingerprint,
            report_sha256=hashlib.sha256(report_payload).hexdigest(),
            entries=tuple(sorted(entries)),
        )


def create_support_bundle(
    report: RuntimeCrashReport,
    path: str | Path,
) -> SupportBundleResult:
    return SupportBundleBuilder(report).write(path)