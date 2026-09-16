from __future__ import annotations

import json
import tempfile
from pathlib import Path

from swirengine.asset_pipeline import AssetPipeline
from swirengine.assets import AssetManager


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="swir-assets-demo-") as directory:
        root = Path(directory)
        texture = root / "hero.texture"
        material = root / "hero.material"
        texture.write_text("neon-blue", encoding="utf-8")
        material.write_text(json.dumps({"name": "hero"}), encoding="utf-8")

        manager = AssetManager(root)
        with AssetPipeline(manager, max_workers=2) as pipeline:
            pipeline.register_processor(
                "material",
                suffixes=(".material",),
                loader=lambda path: json.loads(path.read_text(encoding="utf-8")),
                dependencies=lambda _path: (texture,),
                finalizer=lambda value: {**value, "ready": True},
            )

            cold = pipeline.wait(pipeline.submit("hero.material"), timeout=2)
            warm = pipeline.wait(pipeline.submit("hero.material"), timeout=2)
            print("cold:", cold.state.value, "cache_hit=", cold.cache_hit, cold.value)
            print("warm:", warm.state.value, "cache_hit=", warm.cache_hit, warm.value)

            manager.invalidate(texture)
            refreshed = pipeline.wait(pipeline.submit("hero.material"), timeout=2)
            print(
                "after dependency invalidation:",
                refreshed.state.value,
                "cache_hit=",
                refreshed.cache_hit,
            )
            print("diagnostics:", pipeline.diagnostics)


if __name__ == "__main__":
    main()
