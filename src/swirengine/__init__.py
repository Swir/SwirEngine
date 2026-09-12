from .assets import AssetDiagnostics, AssetInfo, AssetManager
from .audio import AudioBackend, AudioEngine, AudioHandle, PygameAudioBackend
from .core.events import EventBus
from .core.game import Game
from .core.scene import Scene
from .debug import DebugOverlay
from .ecs import ECSWorld, Entity
from .graphics.animation import AnimatedSprite2D, AnimationClip, SpriteSheet, animated_sprite
from .graphics.camera import Camera2D
from .graphics.camera3d import Camera3D
from .graphics.gltf import GltfSceneMesh, load_gltf, load_gltf_scene
from .graphics.gltf_asset import GltfPrimitiveAsset, load_gltf_material, load_gltf_primitives
from .graphics.lights import (
    MAX_DIRECTIONAL_LIGHTS,
    MAX_POINT_LIGHTS,
    MAX_SPOT_LIGHTS,
    DirectionalLight3D,
    LightSelection3D,
    PointLight3D,
    SpotLight3D,
    select_lights,
)
from .graphics.material import Material3D
from .graphics.mesh import Mesh3D, MeshData, cube_mesh
from .graphics.obj import load_obj
from .graphics.primitives import Cube3D, Rectangle2D, Sprite2D, Text2D
from .graphics.stats import RendererStats
from .hotreload import (
    HotReloadSnapshot,
    HotReloadStateError,
    HotReloadStateRegistry,
)
from .math.types import Color, Transform, Vec2, Vec3
from .particles import ParticleEmitter2D
from .physics.collision2d import AABB, BoxCollider2D, CollisionWorld2D
from .physics.rigidbody2d import PhysicsWorld2D, RigidBody2D
from .plugins import PluginError, PluginInfo, PluginManager
from .prefab import Prefab, PrefabInstance, PrefabOverrides, PrefabSelector
from .profiler import FrameProfile, Profiler
from .serialization import SceneCodecRegistry, SceneSerializationError, SceneSerializer
from .storage import SaveStore
from .tilemap import TileMap2D
from .ui import UIButton, UILabel, UIManager, UIPanel, UIProgressBar

__all__ = [
    "AABB",
    "MAX_DIRECTIONAL_LIGHTS",
    "MAX_POINT_LIGHTS",
    "MAX_SPOT_LIGHTS",
    "AnimatedSprite2D",
    "AnimationClip",
    "AssetDiagnostics",
    "AssetInfo",
    "AssetManager",
    "AudioBackend",
    "AudioEngine",
    "AudioHandle",
    "BoxCollider2D",
    "Camera2D",
    "Camera3D",
    "CollisionWorld2D",
    "Color",
    "Cube3D",
    "DebugOverlay",
    "DirectionalLight3D",
    "ECSWorld",
    "Entity",
    "EventBus",
    "FrameProfile",
    "Game",
    "GltfPrimitiveAsset",
    "GltfSceneMesh",
    "HotReloadSnapshot",
    "HotReloadStateError",
    "HotReloadStateRegistry",
    "LightSelection3D",
    "Material3D",
    "Mesh3D",
    "MeshData",
    "ParticleEmitter2D",
    "PhysicsWorld2D",
    "PluginError",
    "PluginInfo",
    "PluginManager",
    "PointLight3D",
    "Prefab",
    "PrefabInstance",
    "PrefabOverrides",
    "PrefabSelector",
    "Profiler",
    "PygameAudioBackend",
    "Rectangle2D",
    "RendererStats",
    "RigidBody2D",
    "SaveStore",
    "Scene",
    "SceneCodecRegistry",
    "SceneSerializationError",
    "SceneSerializer",
    "SpotLight3D",
    "Sprite2D",
    "SpriteSheet",
    "Text2D",
    "TileMap2D",
    "Transform",
    "UIButton",
    "UILabel",
    "UIManager",
    "UIPanel",
    "UIProgressBar",
    "Vec2",
    "Vec3",
    "animated_sprite",
    "cube_mesh",
    "load_gltf",
    "load_gltf_material",
    "load_gltf_primitives",
    "load_gltf_scene",
    "load_obj",
    "select_lights",
]

__version__ = "0.4.15"
