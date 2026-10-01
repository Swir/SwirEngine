from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from .multiplayer20 import ProductionMultiplayerSession
from .multiplayer_debugger22 import (
    MAX_MULTIPLAYER_DEBUG_CAPTURE_BYTES_22,
    MULTIPLAYER_DEBUG_CAPTURE_FORMAT_22,
    MULTIPLAYER_DEBUG_CAPTURE_VERSION_22,
    MultiplayerDebugger22,
    MultiplayerDebuggerError22,
    MultiplayerDebuggerLimits22,
    RoundTripProbeSource22,
)
from .network_profiler16 import MultiplayerNetworkProfiler

DEFAULT_MULTIPLAYER_DEBUG_CAPTURE_PATH_22 = (
    ".swir/multiplayer-debugger/capture.json"
)

_WINDOWS_UNSAFE_CHARACTERS_22 = frozenset('<>:"|?*')
_WINDOWS_RESERVED_NAMES_22 = frozenset(
    {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{number}" for number in range(1, 10)),
        *(f"lpt{number}" for number in range(1, 10)),
    }
)


class EditorMultiplayerDebuggerError22(RuntimeError):
    """Sanitized editor debugger failure with a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


_PUBLIC_FAILURE_CODES_22 = frozenset(
    {
        "attach_failed",
        "capture_failed",
        "capture_limit_too_small",
        "capture_too_large",
        "capture_write_failed",
        "client_limit_reached",
        "client_unavailable",
        "debugger_closed",
        "diagnostic_source_limit",
        "diagnostic_source_unavailable",
        "fingerprint_failed",
        "invalid_capture",
        "invalid_capture_path",
        "invalid_project_root",
        "round_trip_attach_failed",
        "round_trip_detach_failed",
        "sample_failed",
        "session_not_attached",
        "snapshot_failed",
        "unsafe_capture_path",
    }
)


def _capture_relative_path(value: str | Path) -> PurePosixPath:
    if not isinstance(value, (str, Path)):
        raise EditorMultiplayerDebuggerError22(
            "invalid_capture_path", "capture path must be a string or Path"
        )
    raw = str(value).strip()
    normalized = raw.replace("\\", "/")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(raw)
    if (
        not normalized
        or normalized == "."
        or posix.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or bool(windows.root)
        or ".." in posix.parts
        or normalized != posix.as_posix()
        or len(posix.parts) < 2
        or posix.parts[0] != ".swir"
    ):
        raise EditorMultiplayerDebuggerError22(
            "invalid_capture_path", "capture path must stay under the project .swir directory"
        )
    if posix.suffix != ".json":
        raise EditorMultiplayerDebuggerError22(
            "invalid_capture_path", "capture path must use the .json suffix"
        )
    for part in posix.parts:
        if (
            not part
            or part in {".", ".."}
            or any(ord(character) < 32 for character in part)
            or any(character in _WINDOWS_UNSAFE_CHARACTERS_22 for character in part)
            or part.endswith((" ", "."))
            or part.split(".", 1)[0].casefold() in _WINDOWS_RESERVED_NAMES_22
        ):
            raise EditorMultiplayerDebuggerError22(
                "invalid_capture_path", "capture path is not portable"
            )
    return posix


class EditorMultiplayerDebugger22:
    """Transient SwirEditor controller for privacy-safe production multiplayer diagnostics.

    The controller owns no project-authored state and is therefore always clean. Captures are
    explicit diagnostic exports confined below ``.swir``; they never participate in the normal
    project save/reopen lifecycle.
    """

    def __init__(self, project_root: str | Path) -> None:
        failure: EditorMultiplayerDebuggerError22 | None = None
        root: Path | None = None
        try:
            root = Path(project_root).expanduser().resolve(strict=True)
        except (OSError, RuntimeError, ValueError):
            failure = EditorMultiplayerDebuggerError22(
                "invalid_project_root", "multiplayer debugger project root is unavailable"
            )
        if failure is not None:
            raise failure
        if root is None:
            raise EditorMultiplayerDebuggerError22(
                "invalid_project_root", "multiplayer debugger project root is unavailable"
            )
        if not root.is_dir():
            raise EditorMultiplayerDebuggerError22(
                "invalid_project_root", "multiplayer debugger project root must be a directory"
            )
        failure = None
        root_stat: os.stat_result | None = None
        try:
            root_stat = root.stat()
        except OSError:
            failure = EditorMultiplayerDebuggerError22(
                "invalid_project_root", "multiplayer debugger project root is unavailable"
            )
        if failure is not None:
            raise failure
        if root_stat is None:
            raise EditorMultiplayerDebuggerError22(
                "invalid_project_root", "multiplayer debugger project root is unavailable"
            )
        self.project_root = root
        self._canonical_project_root = root
        self._project_root_identity = (root_stat.st_dev, root_stat.st_ino)
        self._debugger: MultiplayerDebugger22 | None = None
        self._closed = False

    @property
    def attached(self) -> bool:
        return self._debugger is not None

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def dirty(self) -> bool:
        return False

    def _require_open(self) -> None:
        if self._closed:
            raise EditorMultiplayerDebuggerError22(
                "debugger_closed", "editor multiplayer debugger is closed"
            )

    def _require_debugger(self) -> MultiplayerDebugger22:
        self._require_open()
        if self._debugger is None:
            raise EditorMultiplayerDebuggerError22(
                "session_not_attached", "no multiplayer session is attached"
            )
        return self._debugger

    @staticmethod
    def _safe_failure(operation: str, exc: Exception) -> EditorMultiplayerDebuggerError22:
        fallback_code = f"{operation}_failed"
        if (
            type(exc) is EditorMultiplayerDebuggerError22
            and type(exc.code) is str
            and exc.code in _PUBLIC_FAILURE_CODES_22
        ):
            return EditorMultiplayerDebuggerError22(
                exc.code, f"multiplayer debugger {operation} was rejected"
            )
        if (
            type(exc) is MultiplayerDebuggerError22
            and type(exc.code) is str
            and exc.code in _PUBLIC_FAILURE_CODES_22
        ):
            return EditorMultiplayerDebuggerError22(
                exc.code, f"multiplayer debugger {operation} was rejected"
            )
        return EditorMultiplayerDebuggerError22(
            fallback_code, f"multiplayer debugger {operation} failed"
        )

    def attach(
        self,
        session: ProductionMultiplayerSession,
        profiler: MultiplayerNetworkProfiler | None = None,
        *,
        limits: MultiplayerDebuggerLimits22 | None = None,
    ) -> dict[str, Any]:
        self._require_open()
        if not isinstance(session, ProductionMultiplayerSession):
            raise TypeError("session must be a ProductionMultiplayerSession")
        if profiler is not None and not isinstance(profiler, MultiplayerNetworkProfiler):
            raise TypeError("profiler must be a MultiplayerNetworkProfiler")
        if limits is not None and not isinstance(limits, MultiplayerDebuggerLimits22):
            raise TypeError("limits must be MultiplayerDebuggerLimits22")
        failure: EditorMultiplayerDebuggerError22 | None = None
        candidate: MultiplayerDebugger22 | None = None
        snapshot: dict[str, Any] | None = None
        try:
            candidate = MultiplayerDebugger22(session, profiler, limits=limits)
            snapshot = candidate.snapshot()
        except Exception as exc:  # noqa: BLE001 - provider error text is private
            failure = self._safe_failure("attach", exc)
        if failure is not None:
            raise failure
        if candidate is None or snapshot is None:
            raise EditorMultiplayerDebuggerError22(
                "attach_failed", "multiplayer debugger attach failed"
            )
        self._debugger = candidate
        return snapshot

    def attach_session(
        self,
        session: ProductionMultiplayerSession,
        profiler: MultiplayerNetworkProfiler | None = None,
        *,
        limits: MultiplayerDebuggerLimits22 | None = None,
    ) -> dict[str, Any]:
        return self.attach(session, profiler, limits=limits)

    def detach(self) -> bool:
        self._require_open()
        attached = self._debugger is not None
        self._debugger = None
        return attached

    def detach_session(self) -> bool:
        return self.detach()

    def sample_peer(self, client_id: str, tick: int, **kwargs: Any) -> dict[str, Any]:
        debugger = self._require_debugger()
        failure: EditorMultiplayerDebuggerError22 | None = None
        snapshot: dict[str, Any] | None = None
        try:
            debugger.sample_peer(client_id, tick, **kwargs)
            snapshot = debugger.snapshot()
        except Exception as exc:  # noqa: BLE001 - provider error text is private
            failure = self._safe_failure("sample", exc)
        if failure is not None:
            raise failure
        if snapshot is None:
            raise EditorMultiplayerDebuggerError22(
                "sample_failed", "multiplayer debugger sample failed"
            )
        return snapshot

    def sample(self, client_id: str, tick: int, **kwargs: Any) -> dict[str, Any]:
        return self.sample_peer(client_id, tick, **kwargs)

    def attach_round_trip_probe(
        self,
        client_id: str,
        probe: RoundTripProbeSource22,
    ) -> dict[str, Any]:
        debugger = self._require_debugger()
        failure: EditorMultiplayerDebuggerError22 | None = None
        snapshot: dict[str, Any] | None = None
        try:
            debugger.attach_round_trip_probe(client_id, probe)
            snapshot = debugger.snapshot()
        except Exception as exc:  # noqa: BLE001 - provider error text is private
            failure = self._safe_failure("round_trip_attach", exc)
        if failure is not None:
            raise failure
        if snapshot is None:
            raise EditorMultiplayerDebuggerError22(
                "round_trip_attach_failed",
                "multiplayer debugger round_trip_attach failed",
            )
        return snapshot

    def detach_round_trip_probe(self, client_id: str) -> bool:
        debugger = self._require_debugger()
        failure: EditorMultiplayerDebuggerError22 | None = None
        detached = False
        try:
            detached = debugger.detach_round_trip_probe(client_id)
        except Exception as exc:  # noqa: BLE001 - provider error text is private
            failure = self._safe_failure("round_trip_detach", exc)
        if failure is not None:
            raise failure
        return detached

    def snapshot(self) -> dict[str, Any]:
        debugger = self._require_debugger()
        failure: EditorMultiplayerDebuggerError22 | None = None
        snapshot: dict[str, Any] | None = None
        try:
            snapshot = debugger.snapshot()
        except Exception as exc:  # noqa: BLE001 - provider error text is private
            failure = self._safe_failure("snapshot", exc)
        if failure is not None:
            raise failure
        if snapshot is None:
            raise EditorMultiplayerDebuggerError22(
                "snapshot_failed", "multiplayer debugger snapshot failed"
            )
        return snapshot

    def capture_bytes(self) -> bytes:
        debugger = self._require_debugger()
        failure: EditorMultiplayerDebuggerError22 | None = None
        payload: bytes | None = None
        try:
            payload = debugger.capture_bytes()
        except Exception as exc:  # noqa: BLE001 - provider error text is private
            failure = self._safe_failure("capture", exc)
        if failure is not None:
            raise failure
        if not isinstance(payload, bytes):
            raise EditorMultiplayerDebuggerError22(
                "invalid_capture", "multiplayer debugger produced an invalid capture"
            )
        maximum = min(
            MAX_MULTIPLAYER_DEBUG_CAPTURE_BYTES_22,
            debugger.limits.max_capture_bytes,
        )
        if len(payload) > maximum:
            raise EditorMultiplayerDebuggerError22(
                "capture_too_large", "multiplayer debugger capture exceeds the byte limit"
            )
        failure = None
        document: object | None = None
        try:
            decoded = payload.decode("ascii")
            document = json.loads(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError):
            failure = EditorMultiplayerDebuggerError22(
                "invalid_capture", "multiplayer debugger produced an invalid capture"
            )
        if failure is not None:
            raise failure
        if (
            not isinstance(document, dict)
            or document.get("format") != MULTIPLAYER_DEBUG_CAPTURE_FORMAT_22
            or document.get("version") != MULTIPLAYER_DEBUG_CAPTURE_VERSION_22
            or document.get("kind") != "capture"
        ):
            raise EditorMultiplayerDebuggerError22(
                "invalid_capture", "multiplayer debugger produced an invalid capture"
            )
        return payload

    def capture_json(self) -> str:
        return self.capture_bytes().decode("ascii")

    def fingerprint(self) -> str:
        debugger = self._require_debugger()
        failure: EditorMultiplayerDebuggerError22 | None = None
        fingerprint: str | None = None
        try:
            fingerprint = debugger.fingerprint()
        except Exception as exc:  # noqa: BLE001 - provider error text is private
            failure = self._safe_failure("fingerprint", exc)
        if failure is not None:
            raise failure
        if (
            not isinstance(fingerprint, str)
            or len(fingerprint) != hashlib.sha256().digest_size * 2
            or any(character not in "0123456789abcdef" for character in fingerprint)
        ):
            raise EditorMultiplayerDebuggerError22(
                "invalid_capture", "multiplayer debugger produced an invalid fingerprint"
            )
        return fingerprint

    def export_capture(
        self,
        path: str | Path = DEFAULT_MULTIPLAYER_DEBUG_CAPTURE_PATH_22,
    ) -> Path:
        self._require_open()
        relative = _capture_relative_path(path)
        payload = self.capture_bytes()
        target = self._prepare_capture_target(relative)
        temporary: Path | None = None
        failure: EditorMultiplayerDebuggerError22 | None = None
        try:
            descriptor, raw_temporary = tempfile.mkstemp(
                prefix=f".{target.stem}.",
                suffix=".tmp",
                dir=target.parent,
            )
            temporary = Path(raw_temporary)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            self._revalidate_capture_target(relative, target)
            os.replace(temporary, target)
            temporary = None
        except EditorMultiplayerDebuggerError22:
            raise
        except (OSError, RuntimeError, ValueError):
            failure = EditorMultiplayerDebuggerError22(
                "capture_write_failed", "multiplayer debugger capture write failed"
            )
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
        if failure is not None:
            raise failure
        return target

    def _validated_project_root(self) -> Path:
        failure: EditorMultiplayerDebuggerError22 | None = None
        resolved: Path | None = None
        root_stat: os.stat_result | None = None
        try:
            if self._canonical_project_root.is_symlink():
                raise EditorMultiplayerDebuggerError22(
                    "unsafe_capture_path", "multiplayer debugger project root was replaced"
                )
            resolved = self._canonical_project_root.resolve(strict=True)
            root_stat = resolved.stat()
        except EditorMultiplayerDebuggerError22:
            raise
        except (OSError, RuntimeError, ValueError):
            failure = EditorMultiplayerDebuggerError22(
                "invalid_project_root", "multiplayer debugger project root is unavailable"
            )
        if failure is not None:
            raise failure
        if resolved is None or root_stat is None:
            raise EditorMultiplayerDebuggerError22(
                "invalid_project_root", "multiplayer debugger project root is unavailable"
            )
        if (
            resolved != self._canonical_project_root
            or not resolved.is_dir()
            or (root_stat.st_dev, root_stat.st_ino) != self._project_root_identity
        ):
            raise EditorMultiplayerDebuggerError22(
                "unsafe_capture_path", "multiplayer debugger project root was replaced"
            )
        return resolved

    def _prepare_capture_target(self, relative: PurePosixPath) -> Path:
        current = self._validated_project_root()
        for part in relative.parts[:-1]:
            current = current / part
            if current.is_symlink():
                raise EditorMultiplayerDebuggerError22(
                    "unsafe_capture_path", "capture path contains a symbolic link"
                )
            failure: EditorMultiplayerDebuggerError22 | None = None
            try:
                current.mkdir(exist_ok=True)
            except OSError:
                failure = EditorMultiplayerDebuggerError22(
                    "capture_write_failed", "multiplayer debugger capture directory is unavailable"
                )
            if failure is not None:
                raise failure
            if current.is_symlink() or not current.is_dir():
                raise EditorMultiplayerDebuggerError22(
                    "unsafe_capture_path", "capture path contains an unsafe directory"
                )
        target = current / relative.name
        self._revalidate_capture_target(relative, target)
        return target

    def _revalidate_capture_target(
        self,
        relative: PurePosixPath,
        target: Path,
    ) -> None:
        root = self._validated_project_root()
        expected_target = root.joinpath(*relative.parts)
        if target != expected_target:
            raise EditorMultiplayerDebuggerError22(
                "unsafe_capture_path", "capture target is not bound to the project root"
            )
        current = root
        for part in relative.parts[:-1]:
            current = current / part
            if current.is_symlink() or not current.is_dir():
                raise EditorMultiplayerDebuggerError22(
                    "unsafe_capture_path", "capture path contains an unsafe directory"
                )
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise EditorMultiplayerDebuggerError22(
                "unsafe_capture_path", "capture target must be a regular file"
            )
        failure: EditorMultiplayerDebuggerError22 | None = None
        try:
            resolved_root = self._validated_project_root()
            resolved_swir = (resolved_root / ".swir").resolve(strict=True)
            resolved_parent = target.parent.resolve(strict=True)
            resolved_target = target.resolve(strict=False)
            resolved_swir.relative_to(resolved_root)
            resolved_parent.relative_to(resolved_swir)
            resolved_target.relative_to(resolved_swir)
        except (OSError, RuntimeError, ValueError):
            failure = EditorMultiplayerDebuggerError22(
                "unsafe_capture_path", "capture path escapes the project .swir directory"
            )
        if failure is not None:
            raise failure

    def close(self) -> None:
        if self._closed:
            return
        self._debugger = None
        self._closed = True


__all__ = [
    "DEFAULT_MULTIPLAYER_DEBUG_CAPTURE_PATH_22",
    "EditorMultiplayerDebugger22",
    "EditorMultiplayerDebuggerError22",
]
