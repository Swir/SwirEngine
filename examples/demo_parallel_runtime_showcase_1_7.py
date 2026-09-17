from __future__ import annotations

from pathlib import Path
import runpy


ROOT = Path(__file__).resolve().parents[1]
DEMO_SCRIPTS = (
    "demo_background_jobs_1_7.py",
    "demo_async_assets_1_7.py",
    "demo_resource_budget_1_7.py",
    "demo_work_graph_1_7.py",
    "demo_scene_staging_1_7.py",
    "demo_background_save_1_7.py",
    "demo_shader_cache_1_7.py",
    "demo_frame_budget_1_7.py",
)


def main() -> None:
    examples = ROOT / "examples"
    for filename in DEMO_SCRIPTS:
        path = examples / filename
        if not path.is_file():
            raise RuntimeError(f"missing verified 1.7 showcase component: {filename}")
        print(f"[parallel-showcase] running {filename}")
        runpy.run_path(str(path), run_name="__main__")
    print(f"[parallel-showcase] PASS: {len(DEMO_SCRIPTS)} verified 1.7 components")


if __name__ == "__main__":
    main()
