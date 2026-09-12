from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any

from .core.scene import Scene
from .graphics.lights import DirectionalLight3D, PointLight3D, SpotLight3D
from .graphics.primitives import Cube3D, Rectangle2D, Sprite2D, Text2D
from .math.types import Color, Transform, Vec2, Vec3
from .prefab import Prefab

SCENE_FORMAT = "swirengine.scene"
PREFAB_FORMAT = "swirengine.prefab"
FORMAT_VERSION = 2
Migration = Callable[[dict[str, Any]], dict[str, Any]]


class SceneSerializationError(ValueError):
    """Raised when scene/prefab data cannot be encoded or decoded safely."""


class SceneCodecRegistry:
    """Allow-list of dataclass types accepted by the scene serializer.

    The registry is intentionally explicit: loading never imports arbitrary classes named by
    JSON. Games and plugins can register their own dataclass scene-object/component types.
    """

    def __init__(self) -> None:
        self._by_name: dict[str, type[Any]] = {}
        self._by_type: dict[type[Any], str] = {}

    def register(self, cls: type[Any], *, name: str | None = None) -> type[Any]:
        if not is_dataclass(cls):
            raise TypeError("scene codec types must be dataclasses")
        type_name = name or f"{cls.__module__}.{cls.__qualname__}"
        existing = self._by_name.get(type_name)
        if existing is not None and existing is not cls:
            raise ValueError(f"scene type name {type_name!r} is already registered")
        existing_name = self._by_type.get(cls)
        if existing_name is not None and existing_name != type_name:
            raise ValueError(f"{cls.__name__} is already registered as {existing_name!r}")
        self._by_name[type_name] = cls
        self._by_type[cls] = type_name
        return cls

    def name_for(self, obj: object) -> str:
        try:
            return self._by_type[type(obj)]
        except KeyError as exc:
            qualified = f"{type(obj).__module__}.{type(obj).__qualname__}"
            raise SceneSerializationError(
                f"unsupported scene object/component type {qualified}; "
                "register the dataclass type with SceneCodecRegistry.register()"
            ) from exc

    def type_for(self, name: str) -> type[Any]:
        try:
            return self._by_name[name]
        except KeyError as exc:
            raise SceneSerializationError(
                f"scene object/component type {name!r} is not registered"
            ) from exc

    @classmethod
    def default(cls) -> SceneCodecRegistry:
        registry = cls()
        for object_type in (
            Rectangle2D,
            Sprite2D,
            Text2D,
            Cube3D,
            DirectionalLight3D,
            PointLight3D,
            SpotLight3D,
        ):
            registry.register(object_type)
        return registry


_VALUE_TYPES: dict[str, type[Any]] = {
    "Color": Color,
    "Transform": Transform,
    "Vec2": Vec2,
    "Vec3": Vec3,
}


def _encode_value(value: Any, refs: dict[int, int]) -> Any:
    reference = refs.get(id(value))
    if reference is not None:
        return {"$ref": reference}
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Path):
        return {"$path": str(value)}
    for name, value_type in _VALUE_TYPES.items():
        if isinstance(value, value_type):
            return {
                "$value": name,
                "data": {
                    field.name: _encode_value(getattr(value, field.name), refs)
                    for field in fields(value)
                },
            }
    if isinstance(value, tuple):
        return {"$tuple": [_encode_value(item, refs) for item in value]}
    if isinstance(value, set):
        encoded = [_encode_value(item, refs) for item in value]
        encoded.sort(key=lambda item: json.dumps(item, sort_keys=True))
        return {"$set": encoded}
    if isinstance(value, list):
        return [_encode_value(item, refs) for item in value]
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise SceneSerializationError("scene dictionaries must use string keys")
        return {key: _encode_value(item, refs) for key, item in value.items()}
    raise SceneSerializationError(f"unsupported scene value type {type(value).__name__}")


def _decode_value(value: Any, objects: list[object]) -> Any:
    if isinstance(value, list):
        return [_decode_value(item, objects) for item in value]
    if not isinstance(value, dict):
        return value
    if "$ref" in value:
        index = value["$ref"]
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(objects):
            raise SceneSerializationError(f"invalid object reference {index!r}")
        return objects[index]
    if "$path" in value:
        return Path(str(value["$path"]))
    if "$tuple" in value:
        return tuple(_decode_value(item, objects) for item in value["$tuple"])
    if "$set" in value:
        return {_decode_value(item, objects) for item in value["$set"]}
    if "$value" in value:
        name = value["$value"]
        try:
            value_type = _VALUE_TYPES[name]
        except KeyError as exc:
            raise SceneSerializationError(f"unknown scene value type {name!r}") from exc
        payload = value.get("data")
        if not isinstance(payload, dict):
            raise SceneSerializationError(f"invalid payload for scene value type {name!r}")
        kwargs = {key: _decode_value(item, objects) for key, item in payload.items()}
        return value_type(**kwargs)
    return {key: _decode_value(item, objects) for key, item in value.items()}


class SceneSerializer:
    """Versioned JSON serializer for scenes, ECS state and reusable prefabs."""

    def __init__(self, registry: SceneCodecRegistry | None = None) -> None:
        self.registry = registry or SceneCodecRegistry.default()
        self._migrations: dict[tuple[str, int], Migration] = {
            (SCENE_FORMAT, 1): self._migrate_scene_v1_to_v2,
            (PREFAB_FORMAT, 1): self._migrate_prefab_v1_to_v2,
        }

    def register_migration(
        self,
        format_name: str,
        from_version: int,
        migration: Migration,
    ) -> None:
        """Register one deterministic ``N -> N+1`` document migration."""
        if from_version < 1:
            raise ValueError("from_version must be >= 1")
        key = (str(format_name), int(from_version))
        if key in self._migrations:
            raise ValueError(f"migration for {key[0]!r} version {key[1]} already exists")
        self._migrations[key] = migration

    @staticmethod
    def _migrate_scene_v1_to_v2(document: dict[str, Any]) -> dict[str, Any]:
        migrated = dict(document)
        migrated.setdefault("ecs", [])
        migrated["version"] = 2
        return migrated

    @staticmethod
    def _migrate_prefab_v1_to_v2(document: dict[str, Any]) -> dict[str, Any]:
        migrated = dict(document)
        migrated["version"] = 2
        return migrated

    def _migrate(self, document: dict[str, Any], expected_format: str) -> dict[str, Any]:
        version = document.get("version")
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise SceneSerializationError(f"invalid {expected_format} version {version!r}")
        if version > FORMAT_VERSION:
            raise SceneSerializationError(
                f"unsupported {expected_format} version {version!r}; newest is {FORMAT_VERSION}"
            )
        migrated = document
        while version < FORMAT_VERSION:
            migration = self._migrations.get((expected_format, version))
            if migration is None:
                raise SceneSerializationError(
                    f"no migration for {expected_format!r} version {version} -> {version + 1}"
                )
            migrated = migration(migrated)
            next_version = migrated.get("version")
            if next_version != version + 1:
                raise SceneSerializationError(
                    f"migration for {expected_format!r} version {version} must produce "
                    f"version {version + 1}"
                )
            version = next_version
        return migrated

    def _encode_dataclass(self, obj: object, refs: dict[int, int]) -> dict[str, Any]:
        type_name = self.registry.name_for(obj)
        data = {
            field.name: _encode_value(getattr(obj, field.name), refs)
            for field in fields(obj)
        }
        return {"type": type_name, "data": data}

    def _encode_objects(self, objects: tuple[object, ...]) -> list[dict[str, Any]]:
        refs = {id(obj): index for index, obj in enumerate(objects)}
        return [self._encode_dataclass(obj, refs) for obj in objects]

    def _decode_dataclass(
        self,
        item: object,
        objects: list[object],
        *,
        label: str,
    ) -> object:
        if not isinstance(item, dict) or not isinstance(item.get("type"), str):
            raise SceneSerializationError(f"each {label} needs a registered type")
        data = item.get("data")
        if not isinstance(data, dict):
            raise SceneSerializationError(f"each {label} needs an object data payload")
        object_type = self.registry.type_for(item["type"])
        obj = object_type.__new__(object_type)
        field_names = {field.name for field in fields(object_type)}
        unknown = set(data) - field_names
        if unknown:
            names = ", ".join(sorted(unknown))
            raise SceneSerializationError(f"unknown fields for {object_type.__name__}: {names}")
        missing = field_names - set(data)
        if missing:
            names = ", ".join(sorted(missing))
            raise SceneSerializationError(f"missing fields for {object_type.__name__}: {names}")
        for field in fields(object_type):
            setattr(obj, field.name, _decode_value(data[field.name], objects))
        post_init = getattr(obj, "__post_init__", None)
        if callable(post_init):
            post_init()
        return obj

    def _decode_objects(self, payload: object) -> tuple[object, ...]:
        if not isinstance(payload, list):
            raise SceneSerializationError("document objects must be a list")
        types: list[type[Any]] = []
        rows: list[dict[str, Any]] = []
        for item in payload:
            if not isinstance(item, dict) or not isinstance(item.get("type"), str):
                raise SceneSerializationError("each scene object needs a registered type")
            data = item.get("data")
            if not isinstance(data, dict):
                raise SceneSerializationError("each scene object needs an object data payload")
            types.append(self.registry.type_for(item["type"]))
            rows.append(data)

        objects = [object_type.__new__(object_type) for object_type in types]
        for obj, object_type, data in zip(objects, types, rows, strict=True):
            field_names = {field.name for field in fields(object_type)}
            unknown = set(data) - field_names
            if unknown:
                names = ", ".join(sorted(unknown))
                raise SceneSerializationError(f"unknown fields for {object_type.__name__}: {names}")
            missing = field_names - set(data)
            if missing:
                names = ", ".join(sorted(missing))
                raise SceneSerializationError(f"missing fields for {object_type.__name__}: {names}")
            for field in fields(object_type):
                setattr(obj, field.name, _decode_value(data[field.name], objects))
            post_init = getattr(obj, "__post_init__", None)
            if callable(post_init):
                post_init()
        return tuple(objects)

    def _encode_ecs(self, scene: Scene, refs: dict[int, int]) -> list[dict[str, Any]]:
        return [
            {
                "id": entity.id,
                "name": entity.name,
                "enabled": entity.enabled,
                "tags": sorted(entity.tags),
                "components": [
                    self._encode_dataclass(component, refs) for component in entity.components
                ],
            }
            for entity in scene.entities
        ]

    def _decode_ecs(self, payload: object, scene: Scene, objects: list[object]) -> None:
        if not isinstance(payload, list):
            raise SceneSerializationError("scene ecs payload must be a list")
        seen_ids: set[int] = set()
        for item in payload:
            if not isinstance(item, dict):
                raise SceneSerializationError("each ECS entity must be an object")
            entity_id = item.get("id")
            if not isinstance(entity_id, int) or isinstance(entity_id, bool) or entity_id < 1:
                raise SceneSerializationError(f"invalid ECS entity id {entity_id!r}")
            if entity_id in seen_ids:
                raise SceneSerializationError(f"duplicate ECS entity id {entity_id}")
            seen_ids.add(entity_id)
            name = item.get("name", "")
            enabled = item.get("enabled", True)
            tags = item.get("tags", [])
            components = item.get("components", [])
            if not isinstance(name, str) or not isinstance(enabled, bool):
                raise SceneSerializationError("invalid ECS entity metadata")
            if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
                raise SceneSerializationError("ECS entity tags must be a list of strings")
            if not isinstance(components, list):
                raise SceneSerializationError("ECS entity components must be a list")
            try:
                entity = scene.ecs.create_entity(
                    entity_id=entity_id,
                    name=name,
                    enabled=enabled,
                    tags=tags,
                )
            except ValueError as exc:
                raise SceneSerializationError(str(exc)) from exc
            for component_payload in components:
                component = self._decode_dataclass(
                    component_payload,
                    objects,
                    label="ECS component",
                )
                entity.add(component)

    def _parse(self, text: str, expected_format: str) -> dict[str, Any]:
        try:
            document = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SceneSerializationError(f"invalid scene JSON: {exc.msg}") from exc
        if not isinstance(document, dict):
            raise SceneSerializationError("scene document must be a JSON object")
        if document.get("format") != expected_format:
            raise SceneSerializationError(f"expected {expected_format!r} document")
        return self._migrate(document, expected_format)

    def dumps_scene(self, scene: Scene, *, indent: int | None = 2) -> str:
        refs = {id(obj): index for index, obj in enumerate(scene.objects)}
        document = {
            "format": SCENE_FORMAT,
            "version": FORMAT_VERSION,
            "objects": self._encode_objects(scene.objects),
            "ecs": self._encode_ecs(scene, refs),
        }
        return json.dumps(document, indent=indent, sort_keys=True) + ("\n" if indent else "")

    def loads_scene(self, text: str, *, scene: Scene | None = None, clear: bool = False) -> Scene:
        document = self._parse(text, SCENE_FORMAT)
        objects = self._decode_objects(document.get("objects"))
        target = scene or Scene()
        if clear:
            target.clear()
        target.add_many(*objects)
        self._decode_ecs(document.get("ecs", []), target, list(objects))
        return target

    def dump_scene(self, scene: Scene, path: str | Path, *, indent: int | None = 2) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.dumps_scene(scene, indent=indent), encoding="utf-8")
        return target

    def load_scene(self, path: str | Path, *, scene: Scene | None = None, clear: bool = False) -> Scene:
        return self.loads_scene(Path(path).read_text(encoding="utf-8"), scene=scene, clear=clear)

    def dumps_prefab(self, prefab: Prefab, *, indent: int | None = 2) -> str:
        document = {
            "format": PREFAB_FORMAT,
            "version": FORMAT_VERSION,
            "name": prefab.name,
            "objects": self._encode_objects(prefab.templates()),
        }
        return json.dumps(document, indent=indent, sort_keys=True) + ("\n" if indent else "")

    def loads_prefab(self, text: str) -> Prefab:
        document = self._parse(text, PREFAB_FORMAT)
        name = document.get("name", "")
        if not isinstance(name, str):
            raise SceneSerializationError("prefab name must be a string")
        objects = self._decode_objects(document.get("objects"))
        if not objects:
            raise SceneSerializationError("prefab document cannot be empty")
        return Prefab(*objects, name=name)

    def dump_prefab(self, prefab: Prefab, path: str | Path, *, indent: int | None = 2) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.dumps_prefab(prefab, indent=indent), encoding="utf-8")
        return target

    def load_prefab(self, path: str | Path) -> Prefab:
        return self.loads_prefab(Path(path).read_text(encoding="utf-8"))
