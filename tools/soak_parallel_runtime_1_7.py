from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCHMARKS = (
    "benchmark_background_jobs_1_7.py",
    "benchmark_async_assets_1_7.py",
    "benchmark_resource_budget_1_7.py",
    "benchmark_work_graph_1_7.py",
    "benchmark_scene_staging_1_7.py",
    "benchmark_background_save_1_7.py",
    "benchmark_shader_cache_1_7.py",
    "benchmark_frame_budget_1_7.py",
)
PER_STAGE_TIMEOUT_SECONDS = 20.0
TOTAL_SOAK_BUDGET_SECONDS = 30.0


def main() -> None:
    tools = ROOT / "tools"
    started = time.perf_counter()
    completed = 0
    for filename in BENCHMARKS:
        path = tools / filename
        if not path.is_file():
            raise RuntimeError(f"missing verified 1.7 workload: {filename}")
        result = subprocess.run(
            [sys.executable, str(path)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=PER_STAGE_TIMEOUT_SECONDS,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"parallel runtime soak stage failed: {filename}\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )
        completed += 1
        print(f"[parallel-soak] PASS {filename}")

    elapsed = time.perf_counter() - started
    if elapsed > TOTAL_SOAK_BUDGET_SECONDS:
        raise RuntimeError(
            f"parallel runtime soak exceeded {TOTAL_SOAK_BUDGET_SECONDS:.1f}s: {elapsed:.4f}s"
        )
    print(
        f"[parallel-soak] PASS: {completed} verified workloads in {elapsed:.4f}s "
        f"(budget {TOTAL_SOAK_BUDGET_SECONDS:.1f}s)"
    )


if __name__ == "__main__":
    main()
