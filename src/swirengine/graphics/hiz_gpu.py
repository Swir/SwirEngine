from __future__ import annotations


class HiZPyramidPass3D:
    """Build a regular-Z maximum depth pyramid on GPU without CPU readback.

    The input is the Renderer2 sampleable depth texture. Each generated R32F level stores the
    maximum depth of the corresponding 2x2 source region, matching the conservative CPU
    `HiZDepthPyramid3D` contract. The chain can be consumed by future GPU bounds/indirect stages or
    inspected by validation tooling without synchronizing every scene object back to Python.
    """

    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self._size: tuple[int, int] | None = None
        self._targets: list[tuple[object, object]] = []
        self._released = False
        self.program = self.ctx.program(
            vertex_shader="""
                #version 330
                void main() {
                    vec2 positions[3] = vec2[](
                        vec2(-1.0, -1.0),
                        vec2(3.0, -1.0),
                        vec2(-1.0, 3.0)
                    );
                    gl_Position = vec4(positions[gl_VertexID], 0.0, 1.0);
                }
            """,
            fragment_shader="""
                #version 330
                uniform sampler2D source_depth;
                uniform ivec2 source_size;
                out float reduced_depth;

                void main() {
                    ivec2 base = ivec2(gl_FragCoord.xy) * 2;
                    ivec2 limit = max(source_size - ivec2(1), ivec2(0));
                    float d0 = texelFetch(source_depth, clamp(base, ivec2(0), limit), 0).r;
                    float d1 = texelFetch(
                        source_depth,
                        clamp(base + ivec2(1, 0), ivec2(0), limit),
                        0
                    ).r;
                    float d2 = texelFetch(
                        source_depth,
                        clamp(base + ivec2(0, 1), ivec2(0), limit),
                        0
                    ).r;
                    float d3 = texelFetch(
                        source_depth,
                        clamp(base + ivec2(1, 1), ivec2(0), limit),
                        0
                    ).r;
                    reduced_depth = max(max(d0, d1), max(d2, d3));
                }
            """,
        )
        self.program["source_depth"].value = 0
        self.vao = self.ctx.vertex_array(self.program, [])

    @property
    def level_count(self) -> int:
        return 0 if self._size is None else 1 + len(self._targets)

    @property
    def textures(self) -> tuple[object, ...]:
        return tuple(texture for texture, _framebuffer in self._targets)

    def _release_targets(self) -> None:
        for texture, framebuffer in self._targets:
            framebuffer.release()
            texture.release()
        self._targets.clear()

    def _ensure_targets(self, width: int, height: int) -> None:
        size = (int(width), int(height))
        if min(size) < 1:
            raise ValueError("Hi-Z GPU dimensions must be greater than zero")
        if self._size == size:
            return
        self._release_targets()
        self._size = size
        current_width, current_height = size
        while current_width > 1 or current_height > 1:
            current_width = max(1, (current_width + 1) // 2)
            current_height = max(1, (current_height + 1) // 2)
            texture = self.ctx.texture((current_width, current_height), 1, dtype="f4")
            texture.filter = (self.ctx.NEAREST, self.ctx.NEAREST)
            texture.repeat_x = False
            texture.repeat_y = False
            framebuffer = self.ctx.framebuffer(color_attachments=[texture])
            self._targets.append((texture, framebuffer))

    @staticmethod
    def _texture_size(texture: object) -> tuple[int, int]:
        raw = getattr(texture, "size", None)
        if raw is None:
            raise TypeError("Hi-Z GPU input must expose a two-dimensional texture size")
        try:
            width, height = raw
        except (TypeError, ValueError) as exc:
            raise TypeError("Hi-Z GPU input must expose a two-dimensional texture size") from exc
        return int(width), int(height)

    def build(self, depth_texture: object, *, width: int, height: int) -> tuple[object, ...]:
        if self._released:
            raise RuntimeError("Hi-Z pyramid pass has been released")
        requested_size = (int(width), int(height))
        if self._texture_size(depth_texture) != requested_size:
            raise ValueError("Hi-Z GPU input texture size must match the requested dimensions")
        self._ensure_targets(*requested_size)
        if not self._targets:
            return ()

        previous_viewport = self.ctx.viewport
        source = depth_texture
        source_width, source_height = requested_size
        try:
            for texture, framebuffer in self._targets:
                target_width, target_height = texture.size
                with self.ctx.scope(framebuffer=framebuffer, enable_only=self.ctx.NOTHING):
                    self.ctx.viewport = (0, 0, target_width, target_height)
                    source.use(location=0)
                    self.program["source_size"].value = (source_width, source_height)
                    self.vao.render(vertices=3)
                source = texture
                source_width = target_width
                source_height = target_height
        finally:
            self.ctx.viewport = previous_viewport
        return self.textures

    def release(self) -> None:
        if self._released:
            return
        self._release_targets()
        self.vao.release()
        self.program.release()
        self._released = True
