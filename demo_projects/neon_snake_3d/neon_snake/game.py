from __future__ import annotations

import math
import os
from collections.abc import Callable

import swirengine as sw

DEMO_VERSION = "1.0.0"
GRID_HALF = 7
CELL_SIZE = 1.05
MOVE_INTERVAL = 0.16
INITIAL_LENGTH = 4
MAX_FRAME_DT = 0.25

Cell = tuple[int, int]
Direction = tuple[int, int]

FOOD_CELLS: tuple[Cell, ...] = (
    (4, 0),
    (4, -4),
    (-3, -4),
    (-5, 2),
    (1, 5),
    (5, 4),
    (2, -5),
    (-4, -2),
    (0, 4),
    (6, -1),
    (-6, 5),
    (3, 3),
)


class NeonSnake3D:
    """Asset-free 3D Snake game built only with public SwirEngine APIs."""

    def __init__(self, game: sw.Game, *, smoke_frames: int = 0) -> None:
        self.game = game
        self.smoke_frames = max(0, int(smoke_frames))
        self.frame_count = 0
        self.elapsed = 0.0
        self.move_accumulator = 0.0
        self.score = 0
        self.high_score = 0
        self.deaths = 0
        self.food_index = 0
        self.direction: Direction = (1, 0)
        self.pending_direction: Direction = self.direction
        self.body_cells: list[Cell] = []
        self.segment_meshes: list[sw.Mesh3D] = []

        self._cube = sw.cube_mesh()
        self._create_world()
        self.reset_round()

    def _mesh(
        self,
        *,
        name: str,
        position: sw.Vec3,
        scale: sw.Vec3,
        material: sw.Material3D,
        tags: set[str] | None = None,
    ) -> sw.Mesh3D:
        mesh = self.game.mesh(
            self._cube,
            name=name,
            color=sw.Color(),
            material=material,
            tags=set() if tags is None else set(tags),
        )
        mesh.position = position
        mesh.scale = scale
        return mesh

    @staticmethod
    def _cell_world(cell: Cell, *, y: float = 0.0) -> sw.Vec3:
        return sw.Vec3(cell[0] * CELL_SIZE, y, cell[1] * CELL_SIZE)

    def _create_world(self) -> None:
        floor_material = sw.Material3D(
            tint=sw.Color(0.025, 0.045, 0.085, 1.0),
            metallic=0.35,
            roughness=0.68,
        )
        wall_material = sw.Material3D(
            tint=sw.Color(0.06, 0.2, 0.55, 1.0),
            metallic=0.6,
            roughness=0.22,
            emissive_factor=sw.Color(0.01, 0.07, 0.3, 1.0),
        )
        self.head_material = sw.Material3D(
            tint=sw.Color(0.16, 1.0, 0.35, 1.0),
            metallic=0.2,
            roughness=0.2,
            emissive_factor=sw.Color(0.02, 0.25, 0.055, 1.0),
        )
        self.body_material = sw.Material3D(
            tint=sw.Color(0.04, 0.68, 0.22, 1.0),
            metallic=0.28,
            roughness=0.3,
            emissive_factor=sw.Color(0.01, 0.12, 0.03, 1.0),
        )
        food_material = sw.Material3D(
            tint=sw.Color(1.0, 0.18, 0.32, 1.0),
            metallic=0.5,
            roughness=0.18,
            emissive_factor=sw.Color(0.35, 0.015, 0.05, 1.0),
        )
        eye_material = sw.Material3D(
            tint=sw.Color(0.7, 0.94, 1.0, 1.0),
            metallic=0.15,
            roughness=0.08,
            emissive_factor=sw.Color(0.22, 0.55, 0.8, 1.0),
        )

        board_extent = (GRID_HALF * 2 + 1) * CELL_SIZE
        self.floor = self._mesh(
            name="snake-arena-floor",
            position=sw.Vec3(0.0, -0.72, 0.0),
            scale=sw.Vec3(board_extent + 1.2, 0.45, board_extent + 1.2),
            material=floor_material,
            tags={"arena"},
        )

        wall_offset = (GRID_HALF + 0.95) * CELL_SIZE
        wall_length = board_extent + 2.0
        wall_specs = (
            (sw.Vec3(0.0, 0.1, -wall_offset), sw.Vec3(wall_length, 1.55, 0.28)),
            (sw.Vec3(0.0, 0.1, wall_offset), sw.Vec3(wall_length, 1.55, 0.28)),
            (sw.Vec3(-wall_offset, 0.1, 0.0), sw.Vec3(0.28, 1.55, wall_length)),
            (sw.Vec3(wall_offset, 0.1, 0.0), sw.Vec3(0.28, 1.55, wall_length)),
        )
        self.walls = [
            self._mesh(
                name=f"snake-wall-{index}",
                position=position,
                scale=scale,
                material=wall_material,
                tags={"arena", "wall"},
            )
            for index, (position, scale) in enumerate(wall_specs)
        ]

        self.head = self._mesh(
            name="snake-head",
            position=sw.Vec3(),
            scale=sw.Vec3(0.86, 0.86, 0.86),
            material=self.head_material,
            tags={"snake", "player", "head"},
        )
        self.eye_left = self._mesh(
            name="snake-eye-left",
            position=sw.Vec3(),
            scale=sw.Vec3(0.15, 0.15, 0.15),
            material=eye_material,
            tags={"snake", "eye"},
        )
        self.eye_right = self._mesh(
            name="snake-eye-right",
            position=sw.Vec3(),
            scale=sw.Vec3(0.15, 0.15, 0.15),
            material=eye_material,
            tags={"snake", "eye"},
        )
        self.food = self._mesh(
            name="snake-food",
            position=sw.Vec3(),
            scale=sw.Vec3(0.58, 0.58, 0.58),
            material=food_material,
            tags={"food", "collectible"},
        )

        self.game.directional_light(
            direction=sw.Vec3(-0.6, -1.0, -0.35),
            color=sw.Color(0.95, 0.98, 1.0, 1.0),
            intensity=2.0,
        )
        self.game.point_light(
            position=sw.Vec3(-5.5, 4.5, -4.0),
            color=sw.Color(0.06, 0.35, 1.0, 1.0),
            intensity=8.0,
            range=15.0,
        )
        self.game.point_light(
            position=sw.Vec3(5.5, 3.8, 5.0),
            color=sw.Color(0.2, 1.0, 0.42, 1.0),
            intensity=7.0,
            range=14.0,
        )
        self.game.point_light(
            position=sw.Vec3(0.0, 3.0, 0.0),
            color=sw.Color(1.0, 0.08, 0.25, 1.0),
            intensity=4.0,
            range=10.0,
        )

    def _ensure_segment_mesh(self, index: int) -> sw.Mesh3D:
        while len(self.segment_meshes) <= index:
            segment_index = len(self.segment_meshes) + 1
            self.segment_meshes.append(
                self._mesh(
                    name=f"snake-body-{segment_index}",
                    position=sw.Vec3(),
                    scale=sw.Vec3(0.76, 0.76, 0.76),
                    material=self.body_material,
                    tags={"snake", "body"},
                )
            )
        return self.segment_meshes[index]

    def _sync_snake_meshes(self) -> None:
        self.head.position = self._cell_world(self.body_cells[0], y=0.02)
        active_body = self.body_cells[1:]
        for index, cell in enumerate(active_body):
            segment = self._ensure_segment_mesh(index)
            segment.visible = True
            segment.position = self._cell_world(cell, y=-0.02)
        for segment in self.segment_meshes[len(active_body) :]:
            segment.visible = False
        self._sync_head_details()

    def _sync_head_details(self) -> None:
        x, z = self.head.position.x, self.head.position.z
        dx, dz = self.direction
        side_x, side_z = -dz, dx
        forward = 0.34
        side = 0.22
        eye_y = 0.23
        self.eye_left.position = sw.Vec3(
            x + dx * forward + side_x * side,
            eye_y,
            z + dz * forward + side_z * side,
        )
        self.eye_right.position = sw.Vec3(
            x + dx * forward - side_x * side,
            eye_y,
            z + dz * forward - side_z * side,
        )
        self.head.rotation.y = math.degrees(math.atan2(dx, -dz))

    def _next_food_cell(self) -> Cell:
        occupied = set(self.body_cells)
        for _ in range(len(FOOD_CELLS)):
            cell = FOOD_CELLS[self.food_index % len(FOOD_CELLS)]
            self.food_index += 1
            if cell not in occupied:
                return cell

        for z in range(-GRID_HALF, GRID_HALF + 1):
            for x in range(-GRID_HALF, GRID_HALF + 1):
                if (x, z) not in occupied:
                    return (x, z)
        return (0, 0)

    def _place_food(self) -> None:
        self.food_cell = self._next_food_cell()
        self.food.position = self._cell_world(self.food_cell, y=0.12)

    def reset_round(self) -> None:
        self.score = 0
        self.move_accumulator = 0.0
        self.direction = (1, 0)
        self.pending_direction = self.direction
        self.body_cells = [(0, 0), (-1, 0), (-2, 0), (-3, 0)]
        self._sync_snake_meshes()
        self._place_food()
        self._update_camera()

    @staticmethod
    def _opposite(a: Direction, b: Direction) -> bool:
        return a[0] == -b[0] and a[1] == -b[1]

    def _read_direction(self, pressed: Callable[[str], bool]) -> None:
        candidates = (
            ((0, -1), "w"),
            ((0, 1), "s"),
            ((-1, 0), "a"),
            ((1, 0), "d"),
        )
        for candidate, key_name in candidates:
            if pressed(key_name) and not self._opposite(candidate, self.direction):
                self.pending_direction = candidate
                return

    def _move_once(self) -> None:
        self.direction = self.pending_direction
        head_x, head_z = self.body_cells[0]
        dx, dz = self.direction
        next_head = (head_x + dx, head_z + dz)

        if abs(next_head[0]) > GRID_HALF or abs(next_head[1]) > GRID_HALF:
            self.deaths += 1
            self.reset_round()
            return

        will_grow = next_head == self.food_cell
        occupied = self.body_cells if will_grow else self.body_cells[:-1]
        if next_head in occupied:
            self.deaths += 1
            self.reset_round()
            return

        self.body_cells.insert(0, next_head)
        if will_grow:
            self.score += 1
            self.high_score = max(self.high_score, self.score)
            self._place_food()
        else:
            self.body_cells.pop()
        self._sync_snake_meshes()

    def _animate_world(self, dt: float) -> None:
        self.elapsed += dt
        self.food.rotation.x += 52.0 * dt
        self.food.rotation.y += 85.0 * dt
        self.food.position.y = 0.15 + math.sin(self.elapsed * 3.2) * 0.16

    def _update_camera(self) -> None:
        self.game.camera.position = sw.Vec3(11.5, 14.5, 14.5)
        self.game.camera.look_at(sw.Vec3(0.0, -0.25, 0.0))

    def step(
        self,
        dt: float,
        pressed: Callable[[str], bool] | None = None,
    ) -> None:
        """Advance deterministic Snake gameplay without requiring an active window."""

        delta = max(0.0, min(float(dt), MAX_FRAME_DT))
        key = self.game.key if pressed is None else pressed
        self._read_direction(key)
        self._animate_world(delta)
        self.move_accumulator += delta
        while self.move_accumulator >= MOVE_INTERVAL:
            self.move_accumulator -= MOVE_INTERVAL
            self._move_once()
        self._update_camera()

        self.frame_count += 1
        if self.smoke_frames and self.frame_count >= self.smoke_frames:
            self.game.stop()


def create_demo_game(*, smoke_frames: int = 0) -> tuple[sw.Game, NeonSnake3D]:
    """Build the complete Neon Snake 3D game with public SwirEngine 1.x APIs."""

    game = sw.Game(
        "Neon Snake 3D - SwirEngine",
        width=1280,
        height=720,
        mode="3d",
        target_fps=120,
    )
    game.configure_postprocess(
        enabled=True,
        tone_mapping="aces",
        exposure=1.08,
        contrast=1.08,
        saturation=1.15,
        vignette=0.12,
        fxaa=True,
    )
    game.configure_shadows(
        enabled=True,
        resolution=1024,
        extent=20.0,
        distance=30.0,
        near=0.1,
        far=70.0,
        bias=0.0016,
        normal_bias=0.0035,
    )

    demo = NeonSnake3D(game, smoke_frames=smoke_frames)

    @game.update
    def update(dt: float) -> None:
        if game.key_pressed("escape"):
            game.stop()
            return
        if game.key_pressed("r"):
            demo.deaths += 1
            demo.reset_round()
        demo.step(dt)

    return game, demo


def main() -> None:
    smoke_frames = int(os.environ.get("SWIR_DEMO_SMOKE_FRAMES", "0") or 0)
    game, _demo = create_demo_game(smoke_frames=smoke_frames)
    print("Neon Snake 3D")
    print("WASD: steer | R: restart | ESC: quit")
    game.run()


if __name__ == "__main__":
    main()
