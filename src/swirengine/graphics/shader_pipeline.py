from __future__ import annotations

import hashlib
import math
import re
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal, TypeAlias

ShaderStage: TypeAlias = Literal["vertex", "fragment"]
DefineValue: TypeAlias = bool | int | float | str
UniformValue: TypeAlias = bool | int | float | tuple[float, ...]

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DEFINE_TOKEN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_BLOCKED_HOOK_TOKENS = (
    "#version",
    "#extension",
    "#include",
    "layout(",
    "gl_fragdepth",
    "gl_clipdistance",
    "imagestore",
    "atomic",
    "buffer ",
    "shared ",
    "barrier(",
    "memorybarrier",
    "subroutine",
)


class ShaderPipelineError(RuntimeError):
    """Base error for creator-facing shader pipeline failures."""


class ShaderSafetyError(ShaderPipelineError, ValueError):
    """Raised when a custom variant attempts to bypass the safe hook contract."""


class ShaderCompileError(ShaderPipelineError):
    """Raised when the graphics backend rejects a prepared shader variant."""


@dataclass(frozen=True, slots=True)
class ShaderHookPoint:
    """Named insertion point explicitly exposed by an engine shader template."""

    name: str
    stage: ShaderStage

    def __post_init__(self) -> None:
        if not _IDENTIFIER.fullmatch(self.name):
            raise ValueError(f"invalid shader hook name: {self.name!r}")
        if self.stage not in ("vertex", "fragment"):
            raise ValueError("shader hook stage must be 'vertex' or 'fragment'")

    @property
    def marker(self) -> str:
        return f"/* SWIR_HOOK:{self.name} */"


@dataclass(frozen=True, slots=True)
class ShaderHook:
    """Creator code supplied for one explicitly allowed template hook."""

    name: str
    source: str

    def __post_init__(self) -> None:
        if not _IDENTIFIER.fullmatch(self.name):
            raise ValueError(f"invalid shader hook name: {self.name!r}")
        object.__setattr__(self, "source", self.source.strip())


@dataclass(frozen=True, slots=True)
class ShaderTemplate:
    """Immutable GLSL template with a finite set of safe creator hook points."""

    name: str
    vertex_source: str
    fragment_source: str
    hook_points: tuple[ShaderHookPoint, ...] = ()

    def __post_init__(self) -> None:
        if not _IDENTIFIER.fullmatch(self.name):
            raise ValueError(f"invalid shader template name: {self.name!r}")
        if not self.vertex_source.strip() or not self.fragment_source.strip():
            raise ValueError("vertex_source and fragment_source must be non-empty")
        seen: set[str] = set()
        for point in self.hook_points:
            if point.name in seen:
                raise ValueError(f"duplicate shader hook point: {point.name}")
            seen.add(point.name)
            source = self.vertex_source if point.stage == "vertex" else self.fragment_source
            if source.count(point.marker) != 1:
                raise ValueError(
                    f"shader hook marker {point.marker!r} must appear exactly once in {point.stage} source"
                )

    @property
    def fingerprint(self) -> str:
        digest = hashlib.sha256()
        digest.update(self.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(self.vertex_source.encode("utf-8"))
        digest.update(b"\0")
        digest.update(self.fragment_source.encode("utf-8"))
        for point in self.hook_points:
            digest.update(b"\0")
            digest.update(point.name.encode("utf-8"))
            digest.update(b":")
            digest.update(point.stage.encode("ascii"))
        return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class ShaderSafetyPolicy:
    """Conservative limits for creator-defined shader variants."""

    max_defines: int = 32
    max_hooks: int = 16
    max_hook_chars: int = 16_384

    def __post_init__(self) -> None:
        if self.max_defines < 0 or self.max_hooks < 0 or self.max_hook_chars < 1:
            raise ValueError("shader safety limits must be non-negative and max_hook_chars >= 1")

    def validate_hook(self, hook: ShaderHook) -> None:
        if len(hook.source) > self.max_hook_chars:
            raise ShaderSafetyError(
                f"shader hook {hook.name!r} exceeds {self.max_hook_chars} characters"
            )
        lowered = hook.source.lower().replace("\t", " ")
        blocked = next((token for token in _BLOCKED_HOOK_TOKENS if token in lowered), None)
        if blocked is not None:
            raise ShaderSafetyError(
                f"shader hook {hook.name!r} contains blocked token {blocked!r}"
            )


@dataclass(frozen=True, slots=True)
class ShaderVariantKey:
    """Compact deterministic key used by the program cache."""

    digest: str


@dataclass(frozen=True, slots=True)
class ShaderVariantSpec:
    """Prepared variant; source expansion happens once, not every frame."""

    template_name: str
    key: ShaderVariantKey
    vertex_source: str
    fragment_source: str
    defines: tuple[tuple[str, str], ...] = ()
    hooks: tuple[str, ...] = ()


@dataclass(slots=True)
class ShaderDiagnostics:
    prepare_requests: int = 0
    compile_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    compile_failures: int = 0
    evictions: int = 0
    invalidations: int = 0
    live_programs: int = 0


@dataclass(slots=True)
class ShaderMaterial3D:
    """A prepared shader variant plus validated creator uniform values."""

    variant: ShaderVariantSpec
    uniforms: dict[str, UniformValue] = field(default_factory=dict)
    strict_uniforms: bool = True

    def __post_init__(self) -> None:
        self.uniforms = {
            self._validate_uniform_name(name): _normalize_uniform_value(value)
            for name, value in self.uniforms.items()
        }

    def set_uniform(self, name: str, value: UniformValue) -> None:
        self.uniforms[self._validate_uniform_name(name)] = _normalize_uniform_value(value)

    def remove_uniform(self, name: str) -> bool:
        return self.uniforms.pop(name, None) is not None

    def apply_uniforms(self, program: object) -> int:
        applied = 0
        for name, value in self.uniforms.items():
            try:
                uniform = program[name]  # type: ignore[index]
            except (KeyError, TypeError):
                if self.strict_uniforms:
                    raise ShaderPipelineError(
                        f"shader program does not expose custom uniform {name!r}"
                    ) from None
                continue
            uniform.value = value
            applied += 1
        return applied

    @staticmethod
    def _validate_uniform_name(name: str) -> str:
        if not _IDENTIFIER.fullmatch(name):
            raise ValueError(f"invalid shader uniform name: {name!r}")
        if name.startswith("gl_"):
            raise ShaderSafetyError("creator uniforms may not use the reserved gl_ prefix")
        return name


class ShaderProgramCache:
    """Bounded LRU cache for prepared shader variants."""

    def __init__(
        self,
        ctx: object,
        *,
        max_programs: int = 64,
        safety: ShaderSafetyPolicy | None = None,
    ) -> None:
        if max_programs < 1:
            raise ValueError("max_programs must be >= 1")
        self.ctx = ctx
        self.max_programs = int(max_programs)
        self.safety = safety or ShaderSafetyPolicy()
        self.diagnostics = ShaderDiagnostics()
        self._programs: OrderedDict[ShaderVariantKey, object] = OrderedDict()

    def prepare(
        self,
        template: ShaderTemplate,
        *,
        defines: Mapping[str, DefineValue] | None = None,
        hooks: Mapping[str, str] | None = None,
    ) -> ShaderVariantSpec:
        self.diagnostics.prepare_requests += 1
        normalized_defines = _normalize_defines(defines or {}, self.safety)
        normalized_hooks = _normalize_hooks(template, hooks or {}, self.safety)
        vertex = template.vertex_source
        fragment = template.fragment_source

        hook_sources = dict(normalized_hooks)
        for point in template.hook_points:
            replacement = hook_sources.get(point.name, "")
            if point.stage == "vertex":
                vertex = vertex.replace(point.marker, replacement)
            else:
                fragment = fragment.replace(point.marker, replacement)

        vertex = _inject_defines(vertex, normalized_defines)
        fragment = _inject_defines(fragment, normalized_defines)
        key = _variant_key(template, normalized_defines, normalized_hooks)
        return ShaderVariantSpec(
            template_name=template.name,
            key=key,
            vertex_source=vertex,
            fragment_source=fragment,
            defines=normalized_defines,
            hooks=tuple(name for name, _ in normalized_hooks),
        )

    def resolve(self, variant: ShaderVariantSpec) -> object:
        self.diagnostics.compile_requests += 1
        cached = self._programs.get(variant.key)
        if cached is not None:
            self._programs.move_to_end(variant.key)
            self.diagnostics.cache_hits += 1
            return cached

        self.diagnostics.cache_misses += 1
        try:
            program = self.ctx.program(  # type: ignore[attr-defined]
                vertex_shader=variant.vertex_source,
                fragment_shader=variant.fragment_source,
            )
        except Exception as exc:  # graphics backends expose different compile exception classes
            self.diagnostics.compile_failures += 1
            raise ShaderCompileError(
                f"failed to compile shader template {variant.template_name!r}: {exc}"
            ) from exc

        self._programs[variant.key] = program
        self._evict_if_needed()
        self.diagnostics.live_programs = len(self._programs)
        return program

    def invalidate(self, variant: ShaderVariantSpec | None = None) -> int:
        if variant is None:
            keys = tuple(self._programs)
        elif variant.key in self._programs:
            keys = (variant.key,)
        else:
            keys = ()
        for key in keys:
            program = self._programs.pop(key)
            _release_program(program)
        if keys:
            self.diagnostics.invalidations += len(keys)
            self.diagnostics.live_programs = len(self._programs)
        return len(keys)

    def release(self) -> None:
        self.invalidate()

    def _evict_if_needed(self) -> None:
        while len(self._programs) > self.max_programs:
            _, program = self._programs.popitem(last=False)
            _release_program(program)
            self.diagnostics.evictions += 1


def _normalize_defines(
    defines: Mapping[str, DefineValue],
    safety: ShaderSafetyPolicy,
) -> tuple[tuple[str, str], ...]:
    if len(defines) > safety.max_defines:
        raise ShaderSafetyError(f"shader variant exceeds {safety.max_defines} defines")
    normalized: list[tuple[str, str]] = []
    for name, value in defines.items():
        if not _IDENTIFIER.fullmatch(name):
            raise ShaderSafetyError(f"invalid shader define name: {name!r}")
        if isinstance(value, bool):
            token = "1" if value else "0"
        elif isinstance(value, int):
            token = str(value)
        elif isinstance(value, float):
            if not math.isfinite(value):
                raise ShaderSafetyError(f"shader define {name!r} must be finite")
            token = format(value, ".9g")
        elif isinstance(value, str) and _DEFINE_TOKEN.fullmatch(value):
            token = value
        else:
            raise ShaderSafetyError(
                f"shader define {name!r} must be bool/int/finite-float or identifier token"
            )
        normalized.append((name, token))
    normalized.sort()
    return tuple(normalized)


def _normalize_hooks(
    template: ShaderTemplate,
    hooks: Mapping[str, str],
    safety: ShaderSafetyPolicy,
) -> tuple[tuple[str, str], ...]:
    if len(hooks) > safety.max_hooks:
        raise ShaderSafetyError(f"shader variant exceeds {safety.max_hooks} hooks")
    allowed = {point.name for point in template.hook_points}
    unknown = sorted(set(hooks) - allowed)
    if unknown:
        raise ShaderSafetyError(f"unknown shader hook(s): {', '.join(unknown)}")
    normalized: list[tuple[str, str]] = []
    for name, source in hooks.items():
        hook = ShaderHook(name, source)
        safety.validate_hook(hook)
        normalized.append((name, hook.source))
    normalized.sort()
    return tuple(normalized)


def _inject_defines(source: str, defines: tuple[tuple[str, str], ...]) -> str:
    if not defines:
        return source
    block = "\n".join(f"#define {name} {value}" for name, value in defines)
    lines = source.splitlines()
    for index, line in enumerate(lines):
        if line.strip().startswith("#version"):
            lines.insert(index + 1, block)
            return "\n".join(lines)
    return f"{block}\n{source}"


def _variant_key(
    template: ShaderTemplate,
    defines: tuple[tuple[str, str], ...],
    hooks: tuple[tuple[str, str], ...],
) -> ShaderVariantKey:
    digest = hashlib.sha256()
    digest.update(template.fingerprint.encode("ascii"))
    for name, value in defines:
        digest.update(b"\0D:")
        digest.update(name.encode("utf-8"))
        digest.update(b"=")
        digest.update(value.encode("utf-8"))
    for name, source in hooks:
        digest.update(b"\0H:")
        digest.update(name.encode("utf-8"))
        digest.update(b"=")
        digest.update(source.encode("utf-8"))
    return ShaderVariantKey(digest.hexdigest())


def _normalize_uniform_value(value: UniformValue) -> UniformValue:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("shader uniform values must be finite")
        return float(value)
    if isinstance(value, tuple) and 1 <= len(value) <= 4:
        result = tuple(float(item) for item in value)
        if not all(math.isfinite(item) for item in result):
            raise ValueError("shader uniform tuple values must be finite")
        return result
    raise TypeError("shader uniform must be bool/int/float or a float tuple of length 1..4")


def _release_program(program: object) -> None:
    release = getattr(program, "release", None)
    if callable(release):
        release()
