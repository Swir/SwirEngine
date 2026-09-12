from dataclasses import dataclass, field

import pytest

from swirengine import Prefab, Rectangle2D, Scene


@dataclass
class Link:
    name: str
    target: object | None = None
    tags: set[str] = field(default_factory=set)


def test_prefab_instances_are_independent_and_preserve_internal_links():
    child = Link("child", tags={"part"})
    root = Link("root", target=child, tags={"root"})
    prefab = Prefab(root, child, name="linked")

    first = prefab.instantiate()
    second = prefab.instantiate()

    assert first.prefab_name == "linked"
    assert first.root is first.objects[0]
    assert first.objects[0] is not root
    assert first.objects[1] is not child
    assert first.objects[0].target is first.objects[1]
    assert second.objects[0].target is second.objects[1]
    assert first.objects[1] is not second.objects[1]

    first.objects[1].tags.add("changed")
    assert "changed" not in second.objects[1].tags
    assert "changed" not in child.tags


def test_prefab_overrides_by_index_and_unique_name_are_deep_copied():
    rect = Rectangle2D(0, 0, 10, 20, name="body", tags={"enemy"})
    prefab = Prefab(rect)
    replacement_tags = {"boss"}

    instance = prefab.instantiate(
        overrides={
            "body": {"x": 50.0},
            0: {"tags": replacement_tags},
        }
    )
    clone = instance.root

    assert clone is not None
    assert clone.x == 50.0
    assert clone.tags == {"boss"}
    replacement_tags.add("mutated")
    assert clone.tags == {"boss"}


def test_prefab_override_validation_is_explicit():
    prefab = Prefab(Link("duplicate"), Link("duplicate"))

    with pytest.raises(KeyError, match="ambiguous"):
        prefab.instantiate(overrides={"duplicate": {"name": "x"}})
    with pytest.raises(KeyError, match="out of range"):
        prefab.instantiate(overrides={9: {"name": "x"}})
    with pytest.raises(AttributeError, match="no prefab-overridable"):
        Prefab(Link("root")).instantiate(overrides={0: {"missing": 1}})


def test_scene_can_capture_instantiate_and_remove_prefab_instance():
    scene = Scene()
    scene.add(Rectangle2D(1, 2, 10, 10, name="keep", tags={"prefab"}))
    scene.add(Rectangle2D(3, 4, 20, 20, name="ignore"))

    prefab = scene.prefab(name="filtered", predicate=lambda obj: "prefab" in obj.tags)
    target = Scene()
    instance = target.instantiate(prefab, overrides={"keep": {"y": 99.0}})

    assert prefab.size == 1
    assert len(target) == 1
    assert target.find("keep") is instance.root
    assert instance.find("keep") is instance.root
    assert instance.root.y == 99.0
    assert instance.tagged("prefab") == (instance.root,)
    assert instance.remove_from(target) == 1
    assert len(target) == 0


def test_prefab_rejects_empty_sources_and_exposes_safe_template_copies():
    with pytest.raises(ValueError, match="requires at least one"):
        Prefab()

    source = Link("root", tags={"original"})
    prefab = Prefab(source)
    templates = prefab.templates()
    templates[0].tags.add("changed")

    assert prefab.instantiate().root.tags == {"original"}
    with pytest.raises(ValueError, match="empty prefab"):
        Scene().prefab()
