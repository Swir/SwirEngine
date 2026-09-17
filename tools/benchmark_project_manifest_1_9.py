from __future__ import annotations

import time
from pathlib import Path
from tempfile import TemporaryDirectory

from swirengine.project19 import ProjectManifest

ITERATIONS = 2_000
BUDGET_SECONDS = 5.0

MANIFEST = """\
name = "Production Workload"
mode = "3d"
engine = ">=1.0,<2.0"
entrypoint = "main.py"

[content]
include = ["assets", "scenes", "scripts"]

[profiles.windows]
target = "windows"
app_name = "Production Workload"
onefile = true
console = false
metadata = { lane = "release", quality = "shipping" }

[profiles.linux]
target = "linux"
app_name = "Production Workload"
onefile = false
console = true

[profiles.macos]
target = "macos"
app_name = "Production Workload"
onefile = false
console = false
"""


def main() -> int:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        for directory in ("assets", "scenes", "scripts"):
            (root / directory).mkdir()
        (root / "main.py").write_text("print('game')\n", encoding="utf-8")
        (root / "swirproject.toml").write_text(MANIFEST, encoding="utf-8")

        started = time.perf_counter()
        fingerprints: set[str] = set()
        for _ in range(ITERATIONS):
            manifest = ProjectManifest.load(root)
            manifest.packaging_profile("windows")
            fingerprints.add(manifest.fingerprint)
        elapsed = time.perf_counter() - started

    if len(fingerprints) != 1:
        raise SystemExit("project manifest fingerprint was not deterministic")
    if elapsed > BUDGET_SECONDS:
        raise SystemExit(
            f"project manifest workload exceeded {BUDGET_SECONDS:.1f}s budget: {elapsed:.4f}s"
        )
    print(
        f"project-manifest workload: {ITERATIONS} parse/profile/fingerprint cycles "
        f"in {elapsed:.4f}s (budget {BUDGET_SECONDS:.1f}s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
