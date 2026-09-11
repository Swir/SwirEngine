from types import SimpleNamespace

from swirengine import DebugOverlay, Profiler, Scene


def test_debug_overlay_updates_screen_space_lines():
    scene = Scene()
    profiler = Profiler()
    overlay = DebugOverlay(scene, profiler, refresh_hz=4)
    overlay.set_enabled()

    profiler.begin_frame()
    profiler.record("update", 0.001)
    stats = SimpleNamespace(
        draw_calls=3,
        sprites=20,
        sprite_batches=1,
        triangles=44,
        directional_lights=1,
        point_lights=2,
        spot_lights=1,
        lights_dropped=3,
    )
    profiler.end_frame(0.02, stats)
    overlay.update(0.3, 1280, 720)

    assert len(overlay.children) == 4
    assert all(line.visible for line in overlay.children)
    assert all(line.screen_space for line in overlay.children)
    assert "FPS" in overlay.children[0].text
    assert "update" in overlay.children[1].text
    assert "sprites 20" in overlay.children[2].text
    assert "D/P/S 1/2/1" in overlay.children[3].text
    assert "dropped 3" in overlay.children[3].text


def test_debug_overlay_toggle_changes_visibility():
    overlay = DebugOverlay(Scene(), Profiler())

    assert overlay.toggle() is True
    assert all(line.visible for line in overlay.children)
    assert overlay.toggle() is False
    assert all(not line.visible for line in overlay.children)
