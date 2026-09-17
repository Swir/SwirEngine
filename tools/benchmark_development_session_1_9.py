from __future__ import annotations

import time
from pathlib import Path
from tempfile import TemporaryDirectory

from swirengine.development19 import DevelopmentRunner

ITERATIONS = 5_000
BUDGET_SECONDS = 5.0

MANIFEST = """\
name = "Run Workload"
mode = "3d"
entrypoint = "main.py"

[run]
arguments = ["--seed", "42", "--level", "benchmark"]
inherit_environment = true

[run.environment]
SWIR_DIAGNOSTICS = "1"
GAME_CHANNEL = "development"
"""


def main() -> int:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        (root / "main.py").write_text("print('game')\n", encoding="utf-8")
        (root / "swirproject.toml").write_text(MANIFEST, encoding="utf-8")
        runner = DevelopmentRunner.load(root)

        started = time.perf_counter()
        fingerprints: set[str] = set()
        for index in range(ITERATIONS):
            plan = runner.plan(extra_arguments=("--frame", str(index % 60)))
            fingerprints.add(plan.configuration_fingerprint)
        elapsed = time.perf_counter() - started

    if len(fingerprints) != 60:
        raise SystemExit(f"expected 60 deterministic run fingerprints, got {len(fingerprints)}")
    if elapsed > BUDGET_SECONDS:
        raise SystemExit(
            f"development-session workload exceeded {BUDGET_SECONDS:.1f}s budget: {elapsed:.4f}s"
        )
    print(
        f"development-session workload: {ITERATIONS} run plans in {elapsed:.4f}s "
        f"(budget {BUDGET_SECONDS:.1f}s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
