from __future__ import annotations

import tempfile
import time
from pathlib import Path

from swirengine.project19 import ProjectManifest
from swirengine.scene_packages19 import ScenePackageRegistry


def _manifest(package_count: int) -> str:
    rows = [
        'name = "Scene Package Benchmark"',
        'mode = "2d"',
        'entrypoint = "main.py"',
        "",
        "[content]",
        'include = ["assets", "scenes", "scripts"]',
        "",
        "[scenes]",
        'boot = "scene00"',
    ]
    for index in range(package_count):
        name = f"scene{index:02d}"
        rows.extend(("", f"[scenes.registry.{name}]", f'path = "scenes/{name}.swirscene"'))
        if index:
            rows.append(f'depends_on = ["scene{index - 1:02d}"]')
    return "\n".join(rows) + "\n"


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="swirengine-scene-plan-") as temporary:
        root = Path(temporary)
        (root / "assets").mkdir()
        (root / "scenes").mkdir()
        (root / "scripts").mkdir()
        (root / "main.py").write_text("print('benchmark')\n", encoding="utf-8")
        (root / "swirproject.toml").write_text(_manifest(64), encoding="utf-8")
        registry = ScenePackageRegistry.load_optional(ProjectManifest.load(root))
        assert registry is not None

        cycles = 5000
        started = time.perf_counter()
        last = None
        for _ in range(cycles):
            last = registry.plan("scene63")
        elapsed = time.perf_counter() - started

        assert last is not None
        assert len(last.ordered_packages) == 64
        assert elapsed < 5.0, f"scene package planning exceeded regression ceiling: {elapsed:.4f}s"
        print(f"{cycles} x 64-package plans: {elapsed:.4f}s")


if __name__ == "__main__":
    main()
