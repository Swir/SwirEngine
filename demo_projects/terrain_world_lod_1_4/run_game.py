from __future__ import annotations

import os

import numpy as np

from swirengine import Color, Game, Material3D, Vec3
from swirengine.terrain import HeightmapTerrain, TerrainCollider3D, TerrainConfig

SMOKE_FRAMES = int(os.environ.get("SWIR_TERRAIN_SMOKE_FRAMES", "0"))


class TerrainWorldLOD14:
    def __init__(self) -> None:
        self.game = Game("SwirEngine 1.4 Terrain + World LOD", 960, 540, mode="3d", vsync=False)
        self.frames = 0
        self.ground_queries = 0

        size = 65
        z, x = np.mgrid[0:size, 0:size]
        heights = (
            np.sin(x * 0.15) * 2.8
            + np.cos(z * 0.12) * 2.2
            + np.sin((x + z) * 0.06) * 1.5
        ).astype("f4")
        self.terrain = HeightmapTerrain(
            heights,
            config=TerrainConfig(
                cell_size=1.5,
                chunk_cells=16,
                lod_steps=(1, 2, 4),
                lod_distances=(28.0, 58.0),
                mesh_cache_size=32,
            ),
        )
        self.collider = TerrainCollider3D(self.terrain)
        self.focus_x = self.terrain.world_width * 0.5
        self.focus_z = self.terrain.world_depth * 0.5

        self.game.camera.position = Vec3(self.focus_x, 42.0, self.focus_z + 48.0)
        self.game.camera.look_at(Vec3(self.focus_x, 0.0, self.focus_z))
        self.material = Material3D(metallic=0.05, roughness=0.88)

        selections = self.terrain.select_chunks(self.focus_x, self.focus_z, radius_chunks=1)
        self.rendered_chunks = len(selections)
        for selection in selections:
            chunk = self.terrain.chunk_mesh(selection.key, selection.lod)
            obj = chunk.to_object(material=self.material)
            obj.color = Color(
                0.12 + selection.lod * 0.08,
                0.48 + selection.lod * 0.07,
                0.18 + selection.lod * 0.05,
                1.0,
            )
            self.game.add(obj)

        self.initial_mesh_builds = self.terrain.diagnostics.mesh_builds
        self.game.directional_light(direction=Vec3(-0.4, -1.0, -0.3), intensity=2.0)
        self.game.update(self._update)

    def _update(self, _dt: float) -> None:
        self.frames += 1
        self.terrain.select_chunks(self.focus_x, self.focus_z, radius_chunks=1)
        hit = self.collider.raycast_down(
            self.focus_x,
            100.0,
            self.focus_z,
            max_distance=200.0,
        )
        if hit is None:
            raise RuntimeError("terrain smoke ground query unexpectedly missed")
        self.ground_queries += 1
        if SMOKE_FRAMES and self.frames >= SMOKE_FRAMES:
            self.game.stop()

    def run(self) -> None:
        self.game.run()
        if SMOKE_FRAMES:
            diagnostics = self.terrain.diagnostics
            assert self.frames >= SMOKE_FRAMES
            assert self.rendered_chunks == 9
            assert self.ground_queries >= SMOKE_FRAMES
            assert diagnostics.mesh_builds == self.initial_mesh_builds
            assert diagnostics.cache_hits >= self.rendered_chunks * SMOKE_FRAMES
            print(
                "Terrain + World LOD 1.4 OpenGL smoke OK: "
                f"frames={self.frames}, chunks={self.rendered_chunks}, "
                f"mesh_builds={diagnostics.mesh_builds}, cache_hits={diagnostics.cache_hits}, "
                f"ground_queries={self.ground_queries}"
            )


if __name__ == "__main__":
    TerrainWorldLOD14().run()
