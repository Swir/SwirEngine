from __future__ import annotations

from swirengine.graphics.shader_pipeline import (
    ShaderHookPoint,
    ShaderMaterial3D,
    ShaderProgramCache,
    ShaderTemplate,
)


class _Uniform:
    def __init__(self) -> None:
        self.value = None


class _Program:
    def __init__(self) -> None:
        self.uniforms = {"pulse": _Uniform()}

    def __getitem__(self, name: str) -> _Uniform:
        return self.uniforms[name]

    def release(self) -> None:
        pass


class _DemoContext:
    """Minimal backend stand-in so the example is runnable without opening a window."""

    def __init__(self) -> None:
        self.compiles = 0

    def program(self, *, vertex_shader: str, fragment_shader: str) -> _Program:
        assert "#version 330" in vertex_shader
        assert "#version 330" in fragment_shader
        self.compiles += 1
        return _Program()


def main() -> None:
    template = ShaderTemplate(
        "creator_surface",
        """#version 330
in vec3 in_pos;
/* SWIR_HOOK:vertex_custom */
void main() { gl_Position = vec4(in_pos, 1.0); }
""",
        """#version 330
uniform float pulse;
out vec4 fragColor;
/* SWIR_HOOK:fragment_custom */
void main() { fragColor = vec4(vec3(pulse), 1.0); }
""",
        hook_points=(
            ShaderHookPoint("vertex_custom", "vertex"),
            ShaderHookPoint("fragment_custom", "fragment"),
        ),
    )

    context = _DemoContext()
    cache = ShaderProgramCache(context, max_programs=8)
    variant = cache.prepare(
        template,
        defines={"USE_CREATOR_EFFECT": True},
        hooks={"fragment_custom": "float creator_gain = 1.0;"},
    )
    material = ShaderMaterial3D(variant, uniforms={"pulse": 0.65})

    first = cache.resolve(variant)
    second = cache.resolve(variant)
    material.apply_uniforms(first)

    print(f"same_program={first is second}")
    print(f"backend_compiles={context.compiles}")
    print(f"cache_hits={cache.diagnostics.cache_hits}")
    print(f"pulse={first['pulse'].value}")


if __name__ == "__main__":
    main()
