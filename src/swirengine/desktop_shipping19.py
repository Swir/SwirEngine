from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .exporting import ExportTarget, NativeBuildResult, ProjectExporter
from .project19 import ProjectManifest

_PLAN_FORMAT = "swirengine.desktop-shipping-plan"
_MANIFEST_FORMAT = "swirengine.desktop-shipping-manifest"
_FORMAT_VERSION = 1
_MAX_INVENTORY_ENTRIES = 20_000
_MAX_TOTAL_BYTES = 16 * 1024 * 1024 * 1024
_MAX_JSON_BYTES = 8 * 1024 * 1024
_MAX_PATH_LENGTH = 512
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_DRIVE_RE = re.compile(r"^[A-Za-z]:")


class DesktopShippingError(ValueError):
    """Raised when a desktop shipping plan or artifact inventory is unsafe or invalid."""


def canonical_desktop_target(platform: str | None = None) -> ExportTarget:
    """Return the desktop target native to ``platform``.

    SwirEngine does not use this helper to imply cross-compilation support: native builds are
    permitted only when the selected target matches this result.
    """

    value = sys.platform if platform is None else str(platform)
    if value == "win32":
        return ExportTarget.WINDOWS
    if value.startswith("linux"):
        return ExportTarget.LINUX
    if value == "darwin":
        return ExportTarget.MACOS
    raise DesktopShippingError(f"unsupported desktop build host: {value}")


def _safe_relative(value: str | Path, *, label: str) -> str:
    raw = str(value).replace("\\", "/").strip()
    if not raw or "\x00" in raw or len(raw) > _MAX_PATH_LENGTH:
        raise DesktopShippingError(
            f"{label} is empty, contains NUL, or exceeds {_MAX_PATH_LENGTH} characters"
        )
    if raw.startswith("/") or raw.startswith("//") or _DRIVE_RE.match(raw):
        raise DesktopShippingError(f"{label} must be project-relative: {value}")
    path = PurePosixPath(raw)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise DesktopShippingError(
            f"{label} must not contain traversal or empty path segments: {value}"
        )
    return path.as_posix()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
        raise DesktopShippingError(f"desktop shipping payload is not portable JSON: {exc}") from exc


def _fingerprint(value: Mapping[str, object]) -> str:
    return hashlib.sha256(_portable_json(value).encode("utf-8")).hexdigest()


def _atomic_write(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as stream:
            stream.write(payload)
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
class ShippingInventoryEntry:
    path: str
    kind: str
    size: int
    sha256: str
    link_target: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _safe_relative(self.path, label="inventory path"))
        if self.kind not in {"file", "symlink"}:
            raise DesktopShippingError("inventory kind must be 'file' or 'symlink'")
        if isinstance(self.size, bool) or not isinstance(self.size, int) or self.size < 0:
            raise DesktopShippingError("inventory size must be a non-negative integer")
        if not _SHA256_RE.fullmatch(self.sha256):
            raise DesktopShippingError("inventory sha256 must be a lowercase 64-character digest")
        target = str(self.link_target)
        if self.kind == "file" and target:
            raise DesktopShippingError("regular-file inventory entries cannot declare link_target")
        if self.kind == "symlink":
            if not target or "\x00" in target or len(target) > _MAX_PATH_LENGTH:
                raise DesktopShippingError(
                    "symlink inventory entries require a bounded link_target"
                )
        object.__setattr__(self, "link_target", target)

    def portable(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "path": self.path,
            "kind": self.kind,
            "size": self.size,
            "sha256": self.sha256,
        }
        if self.kind == "symlink":
            payload["link_target"] = self.link_target
        return payload

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ShippingInventoryEntry:
        try:
            size = data["size"]
            if isinstance(size, bool) or not isinstance(size, int):
                raise TypeError("inventory size is not an integer")
            return cls(
                path=str(data["path"]),
                kind=str(data["kind"]),
                size=size,
                sha256=str(data["sha256"]),
                link_target=str(data.get("link_target", "")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise DesktopShippingError("invalid desktop shipping inventory entry") from exc


def _validate_inventory(
    entries: Sequence[ShippingInventoryEntry],
) -> tuple[ShippingInventoryEntry, ...]:
    values = tuple(entries)
    if len(values) > _MAX_INVENTORY_ENTRIES:
        raise DesktopShippingError(
            f"desktop shipping inventory exceeds {_MAX_INVENTORY_ENTRIES} entries"
        )
    if not all(isinstance(entry, ShippingInventoryEntry) for entry in values):
        raise DesktopShippingError("desktop shipping inventory contains an invalid entry")
    keys = [entry.path.casefold() for entry in values]
    if len(keys) != len(set(keys)):
        raise DesktopShippingError(
            "desktop shipping inventory contains case-folded path collisions"
        )
    if sum(entry.size for entry in values) > _MAX_TOTAL_BYTES:
        raise DesktopShippingError(f"desktop shipping inventory exceeds {_MAX_TOTAL_BYTES} bytes")
    return tuple(sorted(values, key=lambda entry: entry.path.casefold()))


def _contained(path: Path, root: Path, *, label: str) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, RuntimeError, ValueError) as exc:
        raise DesktopShippingError(f"{label} resolves outside its allowed root: {path}") from exc


def _source_inventory(root: Path, files: Sequence[Path]) -> tuple[ShippingInventoryEntry, ...]:
    entries: list[ShippingInventoryEntry] = []
    root = root.resolve()
    for relative in files:
        portable = _safe_relative(relative, label="source file")
        source = root / PurePosixPath(portable)
        _contained(source, root, label="source file")
        if source.is_symlink():
            raise DesktopShippingError(
                f"source shipping inventory does not accept symlinked files: {portable}"
            )
        if not source.is_file():
            raise DesktopShippingError(
                f"source shipping file is missing or not regular: {portable}"
            )
        entries.append(
            ShippingInventoryEntry(
                path=portable,
                kind="file",
                size=source.stat().st_size,
                sha256=_sha256(source),
            )
        )
    return _validate_inventory(entries)


def _artifact_inventory(root: Path) -> tuple[ShippingInventoryEntry, ...]:
    root = root.resolve()
    if not root.is_dir():
        raise DesktopShippingError(f"native artifact root does not exist: {root}")
    entries: list[ShippingInventoryEntry] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().casefold()):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            try:
                target = os.readlink(path)
            except OSError as exc:
                raise DesktopShippingError(f"cannot read artifact symlink: {relative}") from exc
            _contained(path, root, label="artifact symlink")
            encoded = target.encode("utf-8", errors="strict")
            entries.append(
                ShippingInventoryEntry(
                    path=relative,
                    kind="symlink",
                    size=len(encoded),
                    sha256=hashlib.sha256(encoded).hexdigest(),
                    link_target=target,
                )
            )
            continue
        if path.is_dir():
            continue
        if not path.is_file():
            raise DesktopShippingError(f"unsupported special artifact entry: {relative}")
        _contained(path, root, label="artifact")
        entries.append(
            ShippingInventoryEntry(
                path=relative,
                kind="file",
                size=path.stat().st_size,
                sha256=_sha256(path),
            )
        )
        if len(entries) > _MAX_INVENTORY_ENTRIES:
            raise DesktopShippingError(
                f"desktop shipping inventory exceeds {_MAX_INVENTORY_ENTRIES} entries"
            )
    return _validate_inventory(entries)


@dataclass(frozen=True, slots=True)
class DesktopShippingPlan:
    project_name: str
    project_fingerprint: str
    profile_name: str
    target: ExportTarget
    app_name: str
    entrypoint: str
    onefile: bool
    console: bool
    source_inventory: tuple[ShippingInventoryEntry, ...]
    format_version: int = _FORMAT_VERSION

    def __post_init__(self) -> None:
        if self.format_version != _FORMAT_VERSION:
            raise DesktopShippingError("unsupported desktop shipping plan format version")
        if not self.target.desktop:
            raise DesktopShippingError("desktop shipping plans require a desktop export target")
        for label, value, maximum in (
            ("project_name", self.project_name, 128),
            ("project_fingerprint", self.project_fingerprint, 128),
            ("profile_name", self.profile_name, 64),
            ("app_name", self.app_name, 128),
        ):
            text = str(value).strip()
            if not text or "\x00" in text or len(text) > maximum:
                raise DesktopShippingError(
                    f"{label} must be non-empty and at most {maximum} characters"
                )
            object.__setattr__(self, label, text)
        object.__setattr__(
            self,
            "entrypoint",
            _safe_relative(self.entrypoint, label="shipping entrypoint"),
        )
        object.__setattr__(self, "source_inventory", _validate_inventory(self.source_inventory))

    @property
    def required_host(self) -> str:
        return {
            ExportTarget.WINDOWS: "windows",
            ExportTarget.LINUX: "linux",
            ExportTarget.MACOS: "macos",
        }[self.target]

    def portable(self) -> dict[str, object]:
        return {
            "format": _PLAN_FORMAT,
            "format_version": self.format_version,
            "project": {
                "name": self.project_name,
                "fingerprint": self.project_fingerprint,
            },
            "profile": {
                "name": self.profile_name,
                "target": self.target.value,
                "app_name": self.app_name,
                "entrypoint": self.entrypoint,
                "onefile": self.onefile,
                "console": self.console,
            },
            "required_host": self.required_host,
            "source_inventory": [entry.portable() for entry in self.source_inventory],
        }

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self.portable())

    def to_json(self, *, indent: int | None = 2) -> str:
        return _portable_json(self.portable(), indent=indent)

    def write(self, path: str | Path) -> Path:
        return _atomic_write(Path(path), (self.to_json(indent=2) + "\n").encode("utf-8"))

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> DesktopShippingPlan:
        if data.get("format") != _PLAN_FORMAT or data.get("format_version") != _FORMAT_VERSION:
            raise DesktopShippingError("unsupported desktop shipping plan format")
        project = data.get("project")
        profile = data.get("profile")
        inventory = data.get("source_inventory")
        if not isinstance(project, Mapping) or not isinstance(profile, Mapping):
            raise DesktopShippingError(
                "desktop shipping plan project/profile sections are malformed"
            )
        if not isinstance(inventory, list):
            raise DesktopShippingError("desktop shipping plan source_inventory must be a list")
        entries: list[ShippingInventoryEntry] = []
        for item in inventory:
            if not isinstance(item, Mapping):
                raise DesktopShippingError(
                    "desktop shipping source inventory entry must be an object"
                )
            entries.append(ShippingInventoryEntry.from_dict(item))
        try:
            onefile = profile["onefile"]
            console = profile["console"]
            if not isinstance(onefile, bool) or not isinstance(console, bool):
                raise TypeError("shipping profile booleans are malformed")
            target = ExportTarget(str(profile["target"]))
            plan = cls(
                project_name=str(project["name"]),
                project_fingerprint=str(project["fingerprint"]),
                profile_name=str(profile["name"]),
                target=target,
                app_name=str(profile["app_name"]),
                entrypoint=str(profile["entrypoint"]),
                onefile=onefile,
                console=console,
                source_inventory=tuple(entries),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise DesktopShippingError(
                "desktop shipping plan is missing required fields"
            ) from exc
        if data.get("required_host") != plan.required_host:
            raise DesktopShippingError(
                "desktop shipping plan required_host is inconsistent with target"
            )
        return plan

    @classmethod
    def load(cls, path: str | Path) -> DesktopShippingPlan:
        return cls.from_dict(_load_json_object(Path(path), label="desktop shipping plan"))


@dataclass(frozen=True, slots=True)
class DesktopShippingManifest:
    plan_fingerprint: str
    target: ExportTarget
    host: str
    python: str
    artifact_root: str
    artifacts: tuple[ShippingInventoryEntry, ...]
    format_version: int = _FORMAT_VERSION

    def __post_init__(self) -> None:
        if self.format_version != _FORMAT_VERSION:
            raise DesktopShippingError("unsupported desktop shipping manifest format version")
        if not self.target.desktop:
            raise DesktopShippingError("desktop shipping manifest target must be desktop")
        if not _SHA256_RE.fullmatch(self.plan_fingerprint):
            raise DesktopShippingError("shipping plan fingerprint must be a SHA-256 digest")
        expected_host = {
            ExportTarget.WINDOWS: "windows",
            ExportTarget.LINUX: "linux",
            ExportTarget.MACOS: "macos",
        }[self.target]
        if self.host != expected_host:
            raise DesktopShippingError(
                "shipping manifest host must match target; cross-build claims are rejected"
            )
        if not re.fullmatch(r"\d+\.\d+", self.python):
            raise DesktopShippingError("shipping manifest python field must be major.minor")
        object.__setattr__(
            self,
            "artifact_root",
            _safe_relative(self.artifact_root, label="artifact_root"),
        )
        object.__setattr__(self, "artifacts", _validate_inventory(self.artifacts))

    def portable(self) -> dict[str, object]:
        return {
            "format": _MANIFEST_FORMAT,
            "format_version": self.format_version,
            "plan_fingerprint": self.plan_fingerprint,
            "target": self.target.value,
            "host": self.host,
            "python": self.python,
            "artifact_root": self.artifact_root,
            "artifacts": [entry.portable() for entry in self.artifacts],
        }

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self.portable())

    def to_json(self, *, indent: int | None = 2) -> str:
        return _portable_json(self.portable(), indent=indent)

    def write(self, path: str | Path) -> Path:
        return _atomic_write(Path(path), (self.to_json(indent=2) + "\n").encode("utf-8"))

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> DesktopShippingManifest:
        if data.get("format") != _MANIFEST_FORMAT or data.get("format_version") != _FORMAT_VERSION:
            raise DesktopShippingError("unsupported desktop shipping manifest format")
        raw_artifacts = data.get("artifacts")
        if not isinstance(raw_artifacts, list):
            raise DesktopShippingError("desktop shipping manifest artifacts must be a list")
        artifacts: list[ShippingInventoryEntry] = []
        for item in raw_artifacts:
            if not isinstance(item, Mapping):
                raise DesktopShippingError(
                    "desktop shipping artifact inventory entry must be an object"
                )
            artifacts.append(ShippingInventoryEntry.from_dict(item))
        try:
            return cls(
                plan_fingerprint=str(data["plan_fingerprint"]),
                target=ExportTarget(str(data["target"])),
                host=str(data["host"]),
                python=str(data["python"]),
                artifact_root=str(data["artifact_root"]),
                artifacts=tuple(artifacts),
            )
        except (KeyError, ValueError) as exc:
            raise DesktopShippingError(
                "desktop shipping manifest is missing required fields"
            ) from exc

    @classmethod
    def load(cls, path: str | Path) -> DesktopShippingManifest:
        return cls.from_dict(_load_json_object(Path(path), label="desktop shipping manifest"))


@dataclass(frozen=True, slots=True)
class DesktopShippingResult:
    plan: DesktopShippingPlan
    build: NativeBuildResult
    plan_path: Path
    manifest: DesktopShippingManifest
    manifest_path: Path


def _load_json_object(path: Path, *, label: str) -> Mapping[str, object]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise DesktopShippingError(f"cannot read {label}: {path}") from exc
    if len(raw) > _MAX_JSON_BYTES:
        raise DesktopShippingError(f"{label} exceeds {_MAX_JSON_BYTES} bytes")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DesktopShippingError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(data, Mapping):
        raise DesktopShippingError(f"{label} root must be a JSON object")
    return data


def create_desktop_shipping_plan(
    manifest: ProjectManifest,
    profile_name: str,
) -> DesktopShippingPlan:
    """Create a checkout-independent source/build contract without executing build tools."""

    if not isinstance(manifest, ProjectManifest):
        raise TypeError("create_desktop_shipping_plan requires a ProjectManifest")
    profile = manifest.packaging_profile(profile_name)
    if not profile.target.desktop:
        raise DesktopShippingError(
            f"profile {profile_name!r} targets {profile.target.value}; "
            "desktop shipping requires windows/linux/macos"
        )
    export_plan = ProjectExporter(manifest.root).plan(profile)
    inventory = _source_inventory(manifest.root, export_plan.files)
    return DesktopShippingPlan(
        project_name=manifest.name,
        project_fingerprint=manifest.fingerprint,
        profile_name=profile.name,
        target=profile.target,
        app_name=profile.effective_app_name,
        entrypoint=profile.entrypoint,
        onefile=profile.onefile,
        console=profile.console,
        source_inventory=inventory,
    )


def build_desktop_shipping(
    manifest: ProjectManifest,
    profile_name: str,
    output_dir: str | Path | None = None,
    *,
    clean: bool = True,
    runner: Any = None,
) -> DesktopShippingResult:
    """Execute a host-native build, then emit a checked source plan and artifact manifest."""

    plan = create_desktop_shipping_plan(manifest, profile_name)
    native_target = canonical_desktop_target()
    if plan.target != native_target:
        raise DesktopShippingError(
            f"{plan.target.value} shipping must run on a matching {plan.required_host} host; "
            f"current native target is {native_target.value}"
        )
    profile = manifest.packaging_profile(profile_name)
    exporter = ProjectExporter(manifest.root)
    kwargs: dict[str, object] = {"clean": clean}
    if runner is not None:
        kwargs["runner"] = runner
    build = exporter.build_native(profile, output_dir, **kwargs)
    artifact_root = build.export.output_dir / "native-dist"
    artifacts = _artifact_inventory(artifact_root)
    if not artifacts:
        raise DesktopShippingError("native desktop build produced an empty artifact inventory")
    manifest_value = DesktopShippingManifest(
        plan_fingerprint=plan.fingerprint,
        target=plan.target,
        host=plan.required_host,
        python=f"{sys.version_info.major}.{sys.version_info.minor}",
        artifact_root="native-dist",
        artifacts=artifacts,
    )
    plan_path = plan.write(build.export.output_dir / "swir-shipping-plan.json")
    manifest_path = manifest_value.write(
        build.export.output_dir / "swir-shipping-manifest.json"
    )
    verify_desktop_shipping(manifest_path, plan_path=plan_path)
    return DesktopShippingResult(
        plan=plan,
        build=build,
        plan_path=plan_path,
        manifest=manifest_value,
        manifest_path=manifest_path,
    )


def verify_desktop_shipping(
    manifest_path: str | Path,
    *,
    plan_path: str | Path | None = None,
) -> DesktopShippingManifest:
    """Verify manifest structure and every current native artifact byte/link target."""

    manifest_file = Path(manifest_path).resolve()
    manifest = DesktopShippingManifest.load(manifest_file)
    if plan_path is not None:
        plan = DesktopShippingPlan.load(plan_path)
        if plan.fingerprint != manifest.plan_fingerprint:
            raise DesktopShippingError(
                "shipping manifest plan fingerprint does not match shipping plan"
            )
        if plan.target != manifest.target:
            raise DesktopShippingError("shipping manifest target does not match shipping plan")
    artifact_root = manifest_file.parent / PurePosixPath(manifest.artifact_root)
    _contained(artifact_root, manifest_file.parent.resolve(), label="artifact root")
    actual = _artifact_inventory(artifact_root)
    expected = {entry.path: entry for entry in manifest.artifacts}
    current = {entry.path: entry for entry in actual}
    if expected.keys() != current.keys():
        missing = sorted(expected.keys() - current.keys())
        unexpected = sorted(current.keys() - expected.keys())
        raise DesktopShippingError(
            f"artifact inventory paths changed; missing={missing[:8]}, unexpected={unexpected[:8]}"
        )
    for path in sorted(expected, key=str.casefold):
        if expected[path] != current[path]:
            raise DesktopShippingError(f"artifact inventory mismatch: {path}")
    return manifest
