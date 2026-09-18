from __future__ import annotations

from tempfile import TemporaryDirectory
from pathlib import Path

from swirengine import Prefab, Rectangle2D, Scene, SceneSerializer
from swirengine.project19 import ProjectManifest
from swirengine.scene_packages19 import ScenePackageLoader, ScenePackageRegistry


MANIFEST = """
name = "Scene Package Demo"
mode = "2d"
entrypoint = "main.py"

[content]
include = ["assets", "scenes", "scripts"]

[scenes]
boot = "title"

[scenes.registry.title]
path = "scenes/title.swirscene"

[scenes.registry.arena]
path = "scenes/arena.swirscene"
prefabs = ["scenes/crate.swirprefab"]
depends_on = ["title"]
""".strip()


def main() -> None:
    with TemporaryDirectory(prefix="swirengine-scene-packages-") as temporary:
        root = Path(temporary)
        for folder in ("assets", "scenes", "scripts"):
            (root / folder).mkdir()
        (root / "main.py").write_text("print('demo')\n", encoding="utf-8")
        (root / "swirproject.toml").write_text(MANIFEST + "\n", encoding="utf-8")

        serializer = SceneSerializer()
        title = Scene()
        title.add(Rectangle2D(0, 0, 320, 90, name="title-card"))
        arena = Scene()
        arena.add(Rectangle2D(30, 40, 24, 24, name="player"))
        serializer.dump_scene(title, root / "scenes" / "title.swirscene")
        serializer.dump_scene(arena, root / "scenes" / "arena.swirscene")
        serializer.dump_prefab(
            Prefab(Rectangle2D(0, 0, 16, 16, name="crate"), name="crate"),
            root / "scenes" / "crate.swirprefab",
        )

        manifest = ProjectManifest.load(root)
        registry = ScenePackageRegistry.load_optional(manifest)
        assert registry is not None
        diagnostics = registry.validate_documents(serializer)
        if diagnostics:
            raise RuntimeError(diagnostics)

        runtime_scene = Scene()
        loader = ScenePackageLoader(registry, serializer)
        boot = loader.transition_to_boot(runtime_scene)
        arena_package = loader.transition(runtime_scene, "arena")
        arena_package.prefabs["scenes/crate.swirprefab"].instantiate(runtime_scene)

        print(f"Registry fingerprint: {registry.fingerprint}")
        print(f"Boot package: {boot.name}")
        print(f"Arena dependency order: {arena_package.plan.ordered_packages}")
        print(f"Runtime objects after transition: {len(runtime_scene.objects)}")


if __name__ == "__main__":
    main()
