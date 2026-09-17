from __future__ import annotations

from types import SimpleNamespace

from swirengine.graphics.primitives import Rectangle2D, Text2D
from swirengine.render_quality18 import DynamicQualityController, default_render_quality_steps
from swirengine.renderer2_bridge18 import Renderer2CompatibilityBridge


class DemoRenderer:
    mode = "2d"
    width = 1280
    height = 720

    def __init__(self) -> None:
        self.frames = 0

    def render(self, scene, *, camera=None, clear_color=(0.035, 0.045, 0.07, 1.0)):
        self.frames += 1


def main() -> None:
    renderer = DemoRenderer()
    quality = DynamicQualityController(default_render_quality_steps(), initial_step="high")
    bridge = Renderer2CompatibilityBridge(renderer, quality=quality)
    scene = SimpleNamespace(
        objects=[
            Rectangle2D(0, 0, 420, 160, layer=0),
            Text2D("SwirEngine 1.8 Renderer2 Bridge", layer=1, screen_space=True),
        ]
    )
    result = bridge.render(scene)
    assert result.frame is not None
    print("execution:", result.execution)
    print("graph passes:", result.frame.graph.passes)
    print("quality:", result.frame.quality_step.name)
    print("diagnostics:", dict(bridge.diagnostics().portable()))


if __name__ == "__main__":
    main()
