from __future__ import annotations

import numpy as np


def main() -> int:
    import moderngl

    from swirengine.graphics.hiz_gpu import HiZPyramidPass3D

    ctx = moderngl.create_standalone_context(require=330, backend="egl")
    depth = ctx.depth_texture((5, 3))
    depth.repeat_x = False
    depth.repeat_y = False
    if hasattr(depth, "compare_func"):
        depth.compare_func = ""
    framebuffer = ctx.framebuffer(depth_attachment=depth)
    framebuffer.use()
    framebuffer.clear(depth=0.42)

    hiz = HiZPyramidPass3D(ctx)
    levels = hiz.build(depth, width=5, height=3)

    if hiz.level_count != 4:
        raise SystemExit(f"unexpected Hi-Z level count: {hiz.level_count}")
    sizes = tuple(texture.size for texture in levels)
    if sizes != ((3, 2), (2, 1), (1, 1)):
        raise SystemExit(f"unexpected Hi-Z sizes: {sizes}")

    terminal = np.frombuffer(levels[-1].read(), dtype="f4")
    if terminal.size != 1 or not np.isclose(float(terminal[0]), 0.42, atol=1e-4):
        raise SystemExit(f"unexpected terminal Hi-Z depth: {terminal.tolist()}")

    hiz.release()
    framebuffer.release()
    depth.release()
    ctx.release()
    print("scene_acceleration_gl: EGL/OpenGL 3.3 depth-texture Hi-Z reduction passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
