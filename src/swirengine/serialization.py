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
FORMAT_VERSION = 3
Migration = Callable[[dict[str, Any]], dict[str, Any]]
ReferenceMap = dict[int, tuple[str, Any]]


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


def _encode_value(value: Any, refs: ReferenceMap) -> Any:
    reference = refs.get(id(value))
    if reference is not None:
        kind, target = reference
        if kind == "object":
            return {"$ref": target}
        if kind == "entity":
            return {"$entity": target}
        if kind == "component":
            entity_id, component_index = target
            return {"$component": [entity_id, component_index]}
        raise SceneSerializationError(f"unknown reference kind {kind!r}")
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


def _decode_value(
    value: Any,
    objects: list[object],
    entities: dict[int, object] | None = None,
    components: dict[tuple[int, int], object] | None = None,
) -> Any:
    if isinstance(value, list):
        return [_decode_value(item, objects, entities, components) for item in value]
    if not isinstance(value, dict):
        return value
    if "$ref" in value:
        index = value["$ref"]
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(objects):
            raise SceneSerializationError(f"invalid object reference {index!r}")
        return objects[index]
    if "$entity" in value:
        entity_id = value["$entity"]
        if not isinstance(entity_id, int) or isinstance(entity_id, bool):
            raise SceneSerializationError(f"invalid entity reference {entity_id!r}")
        if entities is None or entity_id not in entities:
            raise SceneSerializationError(f"unknown entity reference {entity_id!r}")
        return entities[entity_id]
    if "$component" in value:
        target = value["$component"]
        if (
            not isinstance(target, list)
            or len(target) != 2
            or not all(isinstance(item, int) and not isinstance(item, bool) for item in target)
        ):
            raise SceneSerializationError(f"invalid component reference {target!r}")
        key = (target[0], target[1])
        if components is None or key not in components:
            raise SceneSerializationError(f"unknown component reference {target!r}")
        return components[key]
    if "$path" in value:
        return Path(str(value["$path"]))
    if "$tuple" in value:
        return tuple(_decode_value(item, objects, entities, components) for item in value["$tuple"])
    if "$set" in value:
        return {_decode_value(item, objects, entities, components) for item in value["$set"]}
    if "$value" in value:
        name = value["$value"]
        try:
            value_type = _VALUE_TYPES[name]
        except KeyError as exc:
            raise SceneSerializationError(f"unknown scene value type {name!r}") from exc
        payload = value.get("data")
        if not isinstance(payload, dict):
            raise SceneSerializationError(f"invalid payload for scene value type {name!r}")
        kwargs = {
            key: _decode_value(item, objects, entities, components)
            for key, item in payload.items()
        }
        return value_type(**kwargs)
    return {
        key: _decode_value(item, objects, entities, components)
        for key, item in value.items()
    }


class SceneSerializer:
    """Versioned JSON serializer for scenes, ECS state and reusable prefabs."""

    def __init__(self, registry: SceneCodecRegistry | None = None) -> None:
        self.registry = registry or SceneCodecRegistry.default()
        self._migrations: dict[tuple[str, int], Migration] = {
            (SCENE_FORMAT, 1): self._migrate_scene_v1_to_v2,
            (SCENE_FORMAT, 2): self._migrate_scene_v2_to_v3,
            (PREFAB_FORMAT, 1): self._migrate_prefab_v1_to_v2,
            (PREFAB_FORMAT, 2): self._migrate_prefab_v2_to_v3,
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
    def _migrate_scene_v2_to_v3(document: dict[str, Any]) -> dict[str, Any]:
        migrated = dict(document)
        migrated["version"] = 3
        return migrated

    @staticmethod
    def _migrate_prefab_v1_to_v2(document: dict[str, Any]) -> dict[str, Any]:
        migrated = dict(document)
        migrated["version"] = 2
        return migrated

    @staticmethod
    def _migrate_prefab_v2_to_v3(document: dict[str, Any]) -> dict[str, Any]:
        migrated = dict(document)
        migrated["version"] = 3
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

    def _encode_dataclass(self, obj: object, refs: ReferenceMap) -> dict[str, Any]:
        type_name = self.registry.name_for(obj)
        data = {
            field.name: _encode_value(getattr(obj, field.name), refs)
            for field in fields(obj)
        }
        return {"type": type_name, "data": data}

    def _encode_objects(
        self,
        objects: tuple[object, ...],
        refs: ReferenceMap | None = None,
    ) -> list[dict[str, Any]]:
        resolved_refs = refs or {
            id(obj): ("object", index) for index, obj in enumerate(objects)
        }
        return [self._encode_dataclass(obj, resolved_refs) for obj in objects]

    @staticmethod
    def _validate_dataclass_payload(
        item: object,
        registry: SceneCodecRegistry,
        *,
        label: str,
    ) -> tuple[type[Any], dict[str, Any]]:
        if not isinstance(item, dict) or not isinstance(item.get("type"), str):
            raise SceneSerializationError(f"each {label} needs a registered type")
        data = item.get("data")
        if not isinstance(data, dict):
            raise SceneSerializationError(f"each {label} needs an object data payload")
        object_type = registry.type_for(item["type"])
        field_names = {field.name for field in fields(object_type)}
        unknown = set(data) - field_names
        if unknown:
            names = ", ".join(sorted(unknown))
            raise SceneSerializationError(f"unknown fields for {object_type.__name__}: {names}")
        missing = field_names - set(data)
        if missing:
            names = ", ".join(sorted(missing))
            raise SceneSerializationError(f"missing fields for {object_type.__name__}: {names}")
        return object_type, data

    @staticmethod
    def _populate_dataclass(
        obj: object,
        object_type: type[Any],
        data: dict[str, Any],
        objects: list[object],
        entities: dict[int, object] | None = None,
        components: dict[tuple[int, int], object] | None = None,
    ) -> None:
        for field in fields(object_type):
            setattr(
                obj,
                field.name,
                _decode_value(data[field.name], objects, entities, components),
            )

    @staticmethod
    def _run_post_init(obj: object) -> None:
        post_init = getattr(obj, "__post_init__", None)
        if callable(post_init):
            post_init()

    def _decode_objects(self, payload: object) -> tuple[object, ...]:
        if not isinstance(payload, list):
            raise SceneSerializationError("document objects must be a list")
        rows = [
            self._validate_dataclass_payload(item, self.registry, label="scene object")
            for item in payload
        ]
        objects = [object_type.__new__(object_type) for object_type, _ in rows]
        for obj, (object_type, data) in zip(objects, rows, strict=True):
            self._populate_dataclass(obj, object_type, data, objects)
        for obj in objects:
            self._run_post_init(obj)
        return tuple(objects)

    @staticmethod
    def _scene_refs(scene: Scene) -> ReferenceMap:
        refs: ReferenceMap = {
            id(obj): ("object", index) for index, obj in enumerate(scene.objects)
        }
        for entity in scene.entities:
            refs[id(entity)] = ("entity", entity.id)
            for component_index, component in enumerate(entity.components):
                refs[id(component)] = ("component", (entity.id, component_index))
        return refs

    def _encode_ecs(self, scene: Scene, refs: ReferenceMap) -> list[dict[str, Any]]:
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
        rows: list[tuple[dict[str, Any], list[tuple[type[Any], dict[str, Any]]]]] = []
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
            component_payloads = item.get("components", [])
            if not isinstance(name, str) or not isinstance(enabled, bool):
                raise SceneSerializationError("invalid ECS entity metadata")
            if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
                raise SceneSerializationError("ECS entity tags must be a list of strings")
            if not isinstance(component_payloads, list):
                raise SceneSerializationError("ECS entity components must be a list")
            component_rows = [
                self._validate_dataclass_payload(
                    component_payload,
                    self.registry,
                    label="ECS component",
                )
                for component_payload in component_payloads
            ]
            rows.append((item, component_rows))

        entities: dict[int, object] = {}
        components: dict[tuple[int, int], object] = {}
        for item, component_rows in rows:
            entity_id = item["id"]
            try:
                entity = scene.ecs.create_entity(
                    entity_id=entity_id,
                    name=item.get("name", ""),
                    enabled=item.get("enabled", True),
                    tags=item.get("tags", []),
                )
            except ValueError as exc:
                raise SceneSerializationError(str(exc)) from exc
            entities[entity_id] = entity
            for component_index, (component_type, _) in enumerate(component_rows):
                components[(entity_id, component_index)] = component_type.__new__(component_type)

        for item, component_rows in rows:
            entity_id = item["id"]
            for component_index, (component_type, data) in enumerate(component_rows):
                component = components[(entity_id, component_index)]
                self._populate_dataclass(
                    component,
                    component_type,
                    data,
                    objects,
                    entities,
                    components,
                )

        for item, component_rows in rows:
            entity_id = item["id"]
            entity = entities[entity_id]
            for component_index, _ in enumerate(component_rows):
                component = components[(entity_id, component_index)]
                self._run_post_init(component)
                try:
                    entity.add(component)  # type: ignore[attr-defined]
                except ValueError as exc:
                    raise SceneSerializationError(str(exc)) from exc

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
        refs = self._scene_refs(scene)
        document = {
            "format": SCENE_FORMAT,
            "version": FORMAT_VERSION,
            "objects": self._encode_objects(scene.objects, refs),
            "ecs": self._encode_ecs(scene, refs),
        }
        return json.dumps(document, indent=indent, sort_keys=True) + ("\n" if indent else "")

    def loads_scene(self, text: str, *, scene: Scene | None = None, clear: bool = False) -> Scene:
        document = self._parse(text, SCENE_FORMAT)
        objects = self._decode_objects(document.get("objects"))
        target = scene if scene is not None else Scene()
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

    def load_scene(
        self, path: str | Path, *, scene: Scene | None = None, clear: bool = False
    ) -> Scene:
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
