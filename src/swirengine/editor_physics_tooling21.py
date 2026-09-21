from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Literal

from .math.types import Vec3
from .physics.collision2d import BoxCollider2D
from .physics.collision3d import BoxCollider3D, SphereCollider3D
from .physics.dynamics3d import PhysicsBody3D, PhysicsMaterial3D
from .physics.rigidbody2d import RigidBody2D

PHYSICS_ASSET_FORMAT = "swirengine.physics-profile"
PHYSICS_ASSET_VERSION = 1
DEFAULT_PHYSICS_PATH = "config/physics.json"

PhysicsDimension21 = Literal["2d", "3d"]
PhysicsShape21 = Literal["box", "sphere"]
PhysicsBodyType21 = Literal["dynamic", "kinematic", "static"]


class EditorPhysicsToolingError(ValueError):
    """Raised when creator physics configuration cannot be authored safely."""


@dataclass(frozen=True, slots=True)
class PhysicsBodySpec21:
    """Portable creator-facing physics body description backed by runtime types."""

    name: str
    dimension: PhysicsDimension21
    shape: PhysicsShape21
    body_type: PhysicsBodyType21 = "dynamic"
    size: tuple[float, ...] = (1.0, 1.0)
    offset: tuple[float, ...] | None = None
    mass: float = 1.0
    gravity_scale: float = 1.0
    linear_damping: float = 0.0
    friction: float = 0.5
    restitution: float = 0.0
    continuous: bool = False
    enabled: bool = True
    layer: int = 1
    mask: int = 0xFFFFFFFF
    tag: str = ""

    def __post_init__(self) -> None:
        name = self.name.strip()
        if not name:
            raise EditorPhysicsToolingError("physics body name cannot be empty")
        object.__setattr__(self, "name", name)
        if self.dimension not in ("2d", "3d"):
            raise EditorPhysicsToolingError("dimension must be '2d' or '3d'")
        if self.shape not in ("box", "sphere"):
            raise EditorPhysicsToolingError("shape must be 'box' or 'sphere'")
        if self.dimension == "2d" and self.shape != "box":
            raise EditorPhysicsToolingError(
                "2D creator physics currently supports box colliders only"
            )
        if self.body_type not in ("dynamic", "kinematic", "static"):
            raise EditorPhysicsToolingError(
                "body_type must be 'dynamic', 'kinematic' or 'static'"
            )

        expected_size = 1 if self.shape == "sphere" else (2 if self.dimension == "2d" else 3)
        expected_offset = 2 if self.dimension == "2d" else 3
        size = _float_tuple(self.size, expected_size, label="size")
        default_offset = (0.0, 0.0) if self.dimension == "2d" else (0.0, 0.0, 0.0)
        offset = _float_tuple(
            default_offset if self.offset is None else self.offset,
            expected_offset,
            label="offset",
        )
        if any(value <= 0.0 for value in size):
            raise EditorPhysicsToolingError("collider dimensions must be greater than zero")
        object.__setattr__(self, "size", size)
        object.__setattr__(self, "offset", offset)

        mass = _finite_float(self.mass, label="mass")
        gravity_scale = _finite_float(self.gravity_scale, label="gravity_scale")
        linear_damping = _finite_float(self.linear_damping, label="linear_damping")
        friction = _finite_float(self.friction, label="friction")
        restitution = _finite_float(self.restitution, label="restitution")
        if mass <= 0.0:
            raise EditorPhysicsToolingError("mass must be greater than zero")
        if linear_damping < 0.0:
            raise EditorPhysicsToolingError("linear_damping must be non-negative")
        if friction < 0.0:
            raise EditorPhysicsToolingError("friction must be non-negative")
        if not 0.0 <= restitution <= 1.0:
            raise EditorPhysicsToolingError("restitution must be between 0 and 1")
        object.__setattr__(self, "mass", mass)
        object.__setattr__(self, "gravity_scale", gravity_scale)
        object.__setattr__(self, "linear_damping", linear_damping)
        object.__setattr__(self, "friction", friction)
        object.__setattr__(self, "restitution", restitution)

        if isinstance(self.layer, bool) or not isinstance(self.layer, int) or self.layer <= 0:
            raise EditorPhysicsToolingError("layer must be a positive integer bit mask")
        if isinstance(self.mask, bool) or not isinstance(self.mask, int) or self.mask < 0:
            raise EditorPhysicsToolingError("mask must be a non-negative integer bit mask")
        object.__setattr__(self, "continuous", bool(self.continuous))
        object.__setattr__(self, "enabled", bool(self.enabled))
        object.__setattr__(self, "tag", str(self.tag))


@dataclass(frozen=True, slots=True)
class EditorPhysicsSnapshot21:
    path: str
    bodies: tuple[PhysicsBodySpec21, ...]
    dirty: bool

    @property
    def body_count(self) -> int:
        return len(self.bodies)

    @property
    def two_d_count(self) -> int:
        return sum(body.dimension == "2d" for body in self.bodies)

    @property
    def three_d_count(self) -> int:
        return sum(body.dimension == "3d" for body in self.bodies)


@dataclass(slots=True)
class _PhysicsTarget2D:
    x: float = 0.0
    y: float = 0.0
    width: float = 1.0
    height: float = 1.0


@dataclass(slots=True)
class _PhysicsTarget3D:
    position: Vec3 = field(default_factory=Vec3)


RuntimePhysicsBody21 = RigidBody2D | PhysicsBody3D


class EditorPhysicsTooling21:
    """Project-scoped collision/rigid-body authoring for SwirEditor 2.1.

    The editor asset is intentionally small and deterministic. Runtime preview construction uses
    the engine's real ``BoxCollider2D``/``RigidBody2D`` and
    ``BoxCollider3D``/``SphereCollider3D``/``PhysicsBody3D`` implementations, preventing the
    creator workflow from drifting into an editor-only physics model.
    """

    def __init__(
        self,
        project_root: str | Path,
        *,
        path: str = DEFAULT_PHYSICS_PATH,
    ) -> None:
        self.project_root = Path(project_root).expanduser().resolve()
        self.relative_path = _project_relative_path(path, label="physics path")
        self._bodies: dict[str, PhysicsBodySpec21] = {}
        self._saved_fingerprint = self._fingerprint()
        target = self.target
        if target.is_file():
            self.load()

    @property
    def target(self) -> Path:
        return _project_target(self.project_root, self.relative_path, label="physics path")

    @property
    def dirty(self) -> bool:
        return self._fingerprint() != self._saved_fingerprint

    def snapshot(self) -> EditorPhysicsSnapshot21:
        return EditorPhysicsSnapshot21(
            path=self.relative_path,
            bodies=tuple(self._bodies[name] for name in sorted(self._bodies)),
            dirty=self.dirty,
        )

    def add_body(self, body: PhysicsBodySpec21) -> EditorPhysicsSnapshot21:
        if not isinstance(body, PhysicsBodySpec21):
            raise TypeError("body must be a PhysicsBodySpec21")
        if body.name in self._bodies:
            raise EditorPhysicsToolingError(f"physics body {body.name!r} already exists")
        self._validate_runtime(body)
        self._bodies[body.name] = body
        return self.snapshot()

    def create_body(
        self,
        name: str,
        *,
        dimension: PhysicsDimension21,
        shape: PhysicsShape21 = "box",
        body_type: PhysicsBodyType21 = "dynamic",
        size: tuple[float, ...] | None = None,
        **changes: Any,
    ) -> EditorPhysicsSnapshot21:
        if size is None:
            if shape == "sphere":
                size = (0.5,)
            elif dimension == "2d":
                size = (1.0, 1.0)
            else:
                size = (1.0, 1.0, 1.0)
        offset = changes.pop("offset", (0.0, 0.0) if dimension == "2d" else (0.0, 0.0, 0.0))
        return self.add_body(
            PhysicsBodySpec21(
                name=name,
                dimension=dimension,
                shape=shape,
                body_type=body_type,
                size=size,
                offset=offset,
                **changes,
            )
        )

    def update_body(self, name: str, **changes: Any) -> EditorPhysicsSnapshot21:
        current = self._require_body(name)
        if "name" in changes and str(changes["name"]).strip() != current.name:
            raise EditorPhysicsToolingError("use rename_body() to change a physics body name")
        updated = replace(current, **changes)
        self._validate_runtime(updated)
        self._bodies[name] = updated
        return self.snapshot()

    def rename_body(self, name: str, new_name: str) -> EditorPhysicsSnapshot21:
        current = self._require_body(name)
        renamed = replace(current, name=new_name)
        if renamed.name != name and renamed.name in self._bodies:
            raise EditorPhysicsToolingError(f"physics body {renamed.name!r} already exists")
        self._validate_runtime(renamed)
        del self._bodies[name]
        self._bodies[renamed.name] = renamed
        return self.snapshot()

    def remove_body(self, name: str) -> EditorPhysicsSnapshot21:
        self._require_body(name)
        del self._bodies[name]
        return self.snapshot()

    def build_runtime(
        self,
        name: str,
        *,
        position: tuple[float, ...] | None = None,
    ) -> RuntimePhysicsBody21:
        return _runtime_body(self._require_body(name), position=position)

    def load(self) -> EditorPhysicsSnapshot21:
        target = self.target
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise EditorPhysicsToolingError(f"cannot load physics configuration: {exc}") from exc
        bodies = _decode_payload(payload)
        self._bodies = {body.name: body for body in bodies}
        self._saved_fingerprint = self._fingerprint()
        return self.snapshot()

    def save(self) -> EditorPhysicsSnapshot21:
        target = self.target
        target.parent.mkdir(parents=True, exist_ok=True)
        # Revalidate after mkdir in case an untrusted project swaps a directory for a symlink.
        target = self.target
        content = self._serialized_text()
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                newline="\n",
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
                temporary = Path(handle.name)
            # Revalidate once more immediately before replacing the destination.
            target = self.target
            os.replace(temporary, target)
            temporary = None
        except OSError as exc:
            raise EditorPhysicsToolingError(f"cannot save physics configuration: {exc}") from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        self._saved_fingerprint = self._fingerprint()
        return self.snapshot()

    def _require_body(self, name: str) -> PhysicsBodySpec21:
        try:
            return self._bodies[str(name)]
        except KeyError as exc:
            raise EditorPhysicsToolingError(f"unknown physics body {name!r}") from exc

    def _validate_runtime(self, body: PhysicsBodySpec21) -> None:
        _runtime_body(body)

    def _payload(self) -> dict[str, Any]:
        return {
            "format": PHYSICS_ASSET_FORMAT,
            "version": PHYSICS_ASSET_VERSION,
            "bodies": [_body_payload(body) for body in self.snapshot().bodies],
        }

    def _serialized_text(self) -> str:
        return json.dumps(
            self._payload(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        ) + "\n"

    def _fingerprint(self) -> str:
        payload = {
            "format": PHYSICS_ASSET_FORMAT,
            "version": PHYSICS_ASSET_VERSION,
            "bodies": [_body_payload(self._bodies[name]) for name in sorted(self._bodies)],
        }
        content = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(content).hexdigest()


def _runtime_body(
    spec: PhysicsBodySpec21,
    *,
    position: tuple[float, ...] | None = None,
) -> RuntimePhysicsBody21:
    if spec.dimension == "2d":
        coordinates = _float_tuple(position or (0.0, 0.0), 2, label="2D position")
        width, height = spec.size
        offset_x, offset_y = spec.offset
        target = _PhysicsTarget2D(
            x=coordinates[0],
            y=coordinates[1],
            width=width,
            height=height,
        )
        collider = BoxCollider2D(
            target,
            width=width,
            height=height,
            offset_x=offset_x,
            offset_y=offset_y,
            enabled=spec.enabled,
            layer=spec.layer,
            mask=spec.mask,
            tag=spec.tag,
        )
        return RigidBody2D(
            target,
            collider,
            body_type=spec.body_type,
            mass=spec.mass,
            gravity_scale=spec.gravity_scale,
            linear_damping=spec.linear_damping,
            restitution=spec.restitution,
            enabled=spec.enabled,
        )

    coordinates = _float_tuple(position or (0.0, 0.0, 0.0), 3, label="3D position")
    target3d = _PhysicsTarget3D(Vec3(*coordinates))
    offset = Vec3(*spec.offset)
    if spec.shape == "box":
        width, height, depth = spec.size
        collider3d = BoxCollider3D(
            target3d,
            width=width,
            height=height,
            depth=depth,
            offset=offset,
            enabled=spec.enabled,
            layer=spec.layer,
            mask=spec.mask,
            tag=spec.tag,
        )
    else:
        (radius,) = spec.size
        collider3d = SphereCollider3D(
            target3d,
            radius=radius,
            offset=offset,
            enabled=spec.enabled,
            layer=spec.layer,
            mask=spec.mask,
            tag=spec.tag,
        )
    return PhysicsBody3D(
        target3d,
        collider3d,
        body_type=spec.body_type,
        mass=spec.mass,
        material=PhysicsMaterial3D(
            friction=spec.friction,
            restitution=spec.restitution,
        ),
        gravity_scale=spec.gravity_scale,
        linear_damping=spec.linear_damping,
        enabled=spec.enabled,
        continuous=spec.continuous,
    )


def _body_payload(body: PhysicsBodySpec21) -> dict[str, Any]:
    payload = asdict(body)
    payload["size"] = list(body.size)
    payload["offset"] = list(body.offset)
    return payload


def _decode_payload(payload: Any) -> tuple[PhysicsBodySpec21, ...]:
    if not isinstance(payload, dict):
        raise EditorPhysicsToolingError("physics configuration root must be a JSON object")
    if payload.get("format") != PHYSICS_ASSET_FORMAT:
        raise EditorPhysicsToolingError("unsupported physics configuration format")
    if payload.get("version") != PHYSICS_ASSET_VERSION:
        raise EditorPhysicsToolingError("unsupported physics configuration version")
    raw_bodies = payload.get("bodies")
    if not isinstance(raw_bodies, list):
        raise EditorPhysicsToolingError("physics configuration bodies must be a JSON array")

    bodies: list[PhysicsBodySpec21] = []
    names: set[str] = set()
    fields = set(PhysicsBodySpec21.__dataclass_fields__)
    for index, raw in enumerate(raw_bodies):
        if not isinstance(raw, dict):
            raise EditorPhysicsToolingError(f"physics body #{index + 1} must be a JSON object")
        unknown = set(raw) - fields
        if unknown:
            raise EditorPhysicsToolingError(
                f"physics body #{index + 1} contains unknown fields: {', '.join(sorted(unknown))}"
            )
        values = dict(raw)
        if "size" in values:
            if not isinstance(values["size"], list):
                raise EditorPhysicsToolingError("physics body size must be a JSON array")
            values["size"] = tuple(values["size"])
        if "offset" in values:
            if not isinstance(values["offset"], list):
                raise EditorPhysicsToolingError("physics body offset must be a JSON array")
            values["offset"] = tuple(values["offset"])
        try:
            body = PhysicsBodySpec21(**values)
        except TypeError as exc:
            raise EditorPhysicsToolingError(
                f"physics body #{index + 1} is missing or has invalid fields: {exc}"
            ) from exc
        if body.name in names:
            raise EditorPhysicsToolingError(f"duplicate physics body name {body.name!r}")
        names.add(body.name)
        _runtime_body(body)
        bodies.append(body)
    return tuple(bodies)


def _finite_float(value: Any, *, label: str) -> float:
    if isinstance(value, bool):
        raise EditorPhysicsToolingError(f"{label} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise EditorPhysicsToolingError(f"{label} must be a finite number") from exc
    if number != number or number in (float("inf"), float("-inf")):
        raise EditorPhysicsToolingError(f"{label} must be a finite number")
    return number


def _float_tuple(value: Any, length: int, *, label: str) -> tuple[float, ...]:
    if not isinstance(value, (tuple, list)) or len(value) != length:
        raise EditorPhysicsToolingError(f"{label} must contain exactly {length} numbers")
    return tuple(_finite_float(item, label=label) for item in value)


def _project_relative_path(value: str | Path, *, label: str) -> str:
    raw = str(value).strip()
    normalized = raw.replace("\\", "/")
    if not normalized or normalized == ".":
        raise EditorPhysicsToolingError(f"{label} cannot be empty")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(raw)
    if (
        posix.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or bool(windows.root)
        or ".." in posix.parts
    ):
        raise EditorPhysicsToolingError(f"{label} must stay project-relative")
    return posix.as_posix()


def _project_target(root: Path, relative: str, *, label: str) -> Path:
    resolved = (root / PurePosixPath(relative)).resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise EditorPhysicsToolingError(f"{label} escapes the project root") from exc
    return resolved