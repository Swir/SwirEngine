from dataclasses import dataclass


@dataclass(slots=True)
class RendererStats:
    draw_calls: int = 0
    sprites: int = 0
    sprite_batches: int = 0
    rectangles: int = 0
    texts: int = 0
    cubes: int = 0
    meshes: int = 0
    shader_meshes: int = 0
    instances: int = 0
    instance_batches: int = 0
    instance_candidates: int = 0
    instances_culled: int = 0
    skinned_meshes: int = 0
    skin_vertices: int = 0
    skin_joints: int = 0
    triangles: int = 0
    directional_lights: int = 0
    point_lights: int = 0
    spot_lights: int = 0
    lights_dropped: int = 0
    texture_uploads: int = 0
    text_uploads: int = 0
    mesh_uploads: int = 0
    texture_cache_entries: int = 0
    text_cache_entries: int = 0

    @property
    def active_lights(self) -> int:
        return self.directional_lights + self.point_lights + self.spot_lights

    def reset(self) -> None:
        self.draw_calls = 0
        self.sprites = 0
        self.sprite_batches = 0
        self.rectangles = 0
        self.texts = 0
        self.cubes = 0
        self.meshes = 0
        self.shader_meshes = 0
        self.instances = 0
        self.instance_batches = 0
        self.instance_candidates = 0
        self.instances_culled = 0
        self.skinned_meshes = 0
        self.skin_vertices = 0
        self.skin_joints = 0
        self.triangles = 0
        self.directional_lights = 0
        self.point_lights = 0
        self.spot_lights = 0
        self.lights_dropped = 0
        self.texture_uploads = 0
        self.text_uploads = 0
        self.mesh_uploads = 0
        self.texture_cache_entries = 0
        self.text_cache_entries = 0
