from .assets import AssetManager
from .audio import AudioBackend, AudioEngine, AudioHandle, PygameAudioBackend
from .core.events import EventBus
from .core.game import Game
from .core.scene import Scene
from .graphics.animation import AnimatedSprite2D, AnimationClip, SpriteSheet, animated_sprite
from .graphics.camera import Camera2D
from .graphics.primitives import Cube3D, Rectangle2D, Sprite2D, Text2D
from .math.types import Color, Transform, Vec2, Vec3
from .particles import ParticleEmitter2D
from .physics.collision2d import AABB, BoxCollider2D, CollisionWorld2D
from .physics.rigidbody2d import PhysicsWorld2D, RigidBody2D
from .storage import SaveStore
from .tilemap import TileMap2D
from .ui import UIButton, UILabel, UIManager, UIPanel, UIProgressBar

__all__ = [
    "AABB",
    "AnimatedSprite2D",
    "AnimationClip",
    "AssetManager",
    "AudioBackend",
    "AudioEngine",
    "AudioHandle",
    "BoxCollider2D",
    "Camera2D",
    "CollisionWorld2D",
    "Color",
    "Cube3D",
    "EventBus",
    "Game",
    "ParticleEmitter2D",
    "PhysicsWorld2D",
    "PygameAudioBackend",
    "Rectangle2D",
    "RigidBody2D",
    "SaveStore",
    "Scene",
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
]

__version__ = "0.3.4"
