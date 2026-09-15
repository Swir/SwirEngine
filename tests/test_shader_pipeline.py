from __future__ import annotations

import pytest

from swirengine.graphics.shader_pipeline import (
    ShaderCompileError,
    ShaderHookPoint,
    ShaderMaterial3D,
    ShaderPipelineError,
    ShaderProgramCache,
    ShaderSafetyError,
    ShaderTemplate,
)


VERTEX = """#version 330
in vec3 in_pos;
/* SWIR_HOOK:vertex_body */
void main() { gl_Position = vec4(in_pos, 1.0); }
"""

FRAGMENT = """#version 330
uniform float pulse;
out vec4 fragColor;
/* SWIR_HOOK:fragment_body */
void main() { fragColor = vec4(pulse); }
"""


class _Uniform:
    def __init__(self) -> None:
        self.value = None


class _Program:
    def __init__(self, uniforms: tuple[str, ...] = ("pulse",)) -> None:
        self.uniforms = {name: _Uniform() for name in uniforms}
        self.released = False

    def __getitem__(self, name: str) -> _Uniform:
        return self.uniforms[name]

    def release(self) -> None:
        self.released = True


class _Context:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.programs: list[_Program] = []
        self.fail_next = False

    def program(self, *, vertex_shader: str, fragment_shader: str) -> _Program:
        self.calls.append((vertex_shader, fragment_shader))
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("compile failed")
        program = _Program()
        self.programs.append(program)
        return program


def _template(name: str = "forward") -> ShaderTemplate:
    return ShaderTemplate(
        name=name,
        vertex_source=VERTEX,
        fragment_source=FRAGMENT,
        hook_points=(
            ShaderHookPoint("vertex_body", "vertex"),
            ShaderHookPoint("fragment_body", "fragment"),
        ),
    )


def test_prepared_variant_resolves_1000_times_with_one_backend_compile():
    ctx = _Context()
    cache = ShaderProgramCache(ctx)
    variant = cache.prepare(_template(), defines={"USE_FOG": True})

    first = cache.resolve(variant)
    for _ in range(999):
        assert cache.resolve(variant) is first

    assert len(ctx.calls) == 1
    assert cache.diagnostics.compile_requests == 1000
    assert cache.diagnostics.cache_misses == 1
    assert cache.diagnostics.cache_hits == 999
    assert cache.diagnostics.live_programs == 1


def test_defines_are_deterministic_and_inserted_after_glsl_version():
    cache = ShaderProgramCache(_Context())
    left = cache.prepare(_template(), defines={"QUALITY": 2, "USE_FOG": True})
    right = cache.prepare(_template(), defines={"USE_FOG": True, "QUALITY": 2})

    assert left.key == right.key
    lines = left.vertex_source.splitlines()
    assert lines[0] == "#version 330"
    assert lines[1:3] == ["#define QUALITY 2", "#define USE_FOG 1"]


def test_safe_hook_is_injected_only_at_declared_point():
    cache = ShaderProgramCache(_Context())
    variant = cache.prepare(
        _template(),
        hooks={"fragment_body": "float creator_gain = 0.75;"},
    )

    assert "float creator_gain = 0.75;" in variant.fragment_source
    assert "SWIR_HOOK:fragment_body" not in variant.fragment_source
    assert "SWIR_HOOK:vertex_body" not in variant.vertex_source
    assert variant.hooks == ("fragment_body",)


def test_unknown_hook_and_engine_state_bypass_are_rejected():
    cache = ShaderProgramCache(_Context())

    with pytest.raises(ShaderSafetyError, match="unknown shader hook"):
        cache.prepare(_template(), hooks={"not_exposed": "float x = 1.0;"})

    with pytest.raises(ShaderSafetyError, match="blocked token"):
        cache.prepare(_template(), hooks={"fragment_body": "gl_FragDepth = 0.0;"})

    with pytest.raises(ShaderSafetyError, match="blocked token"):
        cache.prepare(_template(), hooks={"fragment_body": "#extension GL_EXT_debug_printf : enable"})


def test_define_tokens_cannot_inject_shader_source():
    cache = ShaderProgramCache(_Context())

    with pytest.raises(ShaderSafetyError, match="must be"):
        cache.prepare(_template(), defines={"MODE": "PBR\n#define OWNED 1"})

    with pytest.raises(ShaderSafetyError, match="invalid shader define name"):
        cache.prepare(_template(), defines={"BAD-NAME": 1})


def test_lru_eviction_releases_old_program_and_keeps_cache_bounded():
    ctx = _Context()
    cache = ShaderProgramCache(ctx, max_programs=2)
    one = cache.prepare(_template(), defines={"MODE": 1})
    two = cache.prepare(_template(), defines={"MODE": 2})
    three = cache.prepare(_template(), defines={"MODE": 3})

    program_one = cache.resolve(one)
    cache.resolve(two)
    cache.resolve(three)

    assert program_one.released
    assert cache.diagnostics.evictions == 1
    assert cache.diagnostics.live_programs == 2
    assert len(ctx.programs) == 3


def test_compile_failure_is_visible_and_does_not_poison_cache():
    ctx = _Context()
    cache = ShaderProgramCache(ctx)
    variant = cache.prepare(_template())
    ctx.fail_next = True

    with pytest.raises(ShaderCompileError, match="compile failed"):
        cache.resolve(variant)

    assert cache.diagnostics.compile_failures == 1
    assert cache.diagnostics.live_programs == 0
    recovered = cache.resolve(variant)
    assert recovered is ctx.programs[-1]
    assert len(ctx.calls) == 2


def test_invalidation_releases_program_and_forces_next_compile():
    ctx = _Context()
    cache = ShaderProgramCache(ctx)
    variant = cache.prepare(_template())
    first = cache.resolve(variant)

    assert cache.invalidate(variant) == 1
    assert first.released
    assert cache.diagnostics.invalidations == 1
    second = cache.resolve(variant)
    assert second is not first
    assert len(ctx.calls) == 2


def test_material_shader_uniforms_are_validated_and_applied():
    cache = ShaderProgramCache(_Context())
    variant = cache.prepare(_template())
    material = ShaderMaterial3D(
        variant,
        uniforms={"pulse": 0.25, "accent": (1.0, 0.5, 0.25)},
        strict_uniforms=False,
    )
    program = _Program(("pulse",))

    assert material.apply_uniforms(program) == 1
    assert program["pulse"].value == 0.25
    material.set_uniform("pulse", 0.75)
    assert material.apply_uniforms(program) == 1
    assert program["pulse"].value == 0.75

    with pytest.raises(ShaderSafetyError, match="reserved gl_"):
        material.set_uniform("gl_Custom", 1.0)


def test_strict_material_uniform_reports_missing_backend_uniform():
    cache = ShaderProgramCache(_Context())
    variant = cache.prepare(_template())
    material = ShaderMaterial3D(variant, uniforms={"missing": 1.0})

    with pytest.raises(ShaderPipelineError, match="missing"):
        material.apply_uniforms(_Program(()))


def test_template_rejects_missing_or_duplicate_hook_contract():
    with pytest.raises(ValueError, match="exactly once"):
        ShaderTemplate(
            "broken",
            VERTEX.replace("/* SWIR_HOOK:vertex_body */", ""),
            FRAGMENT,
            (ShaderHookPoint("vertex_body", "vertex"),),
        )

    with pytest.raises(ValueError, match="duplicate"):
        ShaderTemplate(
            "duplicate",
            VERTEX,
            FRAGMENT,
            (
                ShaderHookPoint("vertex_body", "vertex"),
                ShaderHookPoint("vertex_body", "vertex"),
            ),
        )
