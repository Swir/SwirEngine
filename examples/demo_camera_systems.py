from swirengine.graphics.camera import Camera2D
from swirengine.graphics.camera_runtime import CameraBounds2D, CameraRail2D, CameraRig2D
from swirengine.math.types import Vec2


camera = Camera2D()
rig = CameraRig2D(
    camera,
    smoothing=8.0,
    dead_zone=Vec2(6.0, 4.0),
    bounds=CameraBounds2D(-20.0, -12.0, 20.0, 12.0),
)
rail = CameraRail2D((Vec2(-12.0, 0.0), Vec2(0.0, 6.0), Vec2(12.0, 0.0)))

for frame in range(121):
    progress = frame / 120.0
    rig.move_on_rail(rail, progress, 1.0 / 60.0)
    if frame == 60:
        rig.shake(1.5, 0.35, frequency=14.0, seed=42.0)
    print(f"frame={frame:03d} camera=({camera.x:6.2f}, {camera.y:6.2f})")
