from __future__ import annotations

import tempfile
import time
from pathlib import Path

from swirengine.project19 import ProjectManifest
from swirengine.run_sessions19 import create_run_plan

ITERATIONS = 5_000
BUDGET_SECONDS = 5.0


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="swirengine-run-session-") as temporary:
        root = Path(temporary)
        for sub in ("assets", "scenes", "scripts"):
            (root / sub).mkdir()
        (root / "main.py").write_text("print('benchmark')\n", encoding="utf-8")
        (root / "swirproject.toml").write_text(
            """
name = "RunSessionBenchmark"
mode = "3d"
entrypoint = "main.py"

[content]
include = ["assets", "scenes", "scripts"]

[run]
arguments = ["--mode", "benchmark"]
inherit_environment = true

[run.environment]
SWIR_BENCHMARK = "1"
""".strip()
            + "\n",
            encoding="utf-8",
        )
        manifest = ProjectManifest.load(root)

        started = time.perf_counter()
        fingerprint = ""
        for index in range(ITERATIONS):
            plan = create_run_plan(
                manifest,
                forwarded_args=("--frame", str(index % 120)),
                environment_overrides=(f"SWIR_ITERATION={index % 17}",),
            )
            fingerprint = plan.fingerprint
        elapsed = time.perf_counter() - started

    print(
        f"run-session workload: {ITERATIONS} plans in {elapsed:.4f}s; "
        f"last={fingerprint[:12]}"
    )
    if elapsed > BUDGET_SECONDS:
        raise SystemExit(
            f"run-session workload exceeded {BUDGET_SECONDS:.1f}s CI ceiling: {elapsed:.4f}s"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
