from __future__ import annotations

import argparse
import tempfile
import time
from pathlib import Path

from swirengine.desktop_shipping19 import create_desktop_shipping_plan
from swirengine.project19 import ProjectManifest


def _fixture(root: Path) -> ProjectManifest:
    root.mkdir()
    (root / "main.py").write_text("print('shipping benchmark')\n", encoding="utf-8")
    assets = root / "assets"
    assets.mkdir()
    for index in range(32):
        (assets / f"asset-{index:02d}.bin").write_bytes((f"asset-{index}" * 8).encode("ascii"))
    (root / "swirproject.toml").write_text(
        """
name = "Shipping Benchmark"
mode = "2d"
entrypoint = "main.py"

[content]
include = ["assets"]

[profiles.linux]
target = "linux"
app_name = "ShippingBenchmark"
include = ["assets"]
onefile = false
console = true
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return ProjectManifest.load(root)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycles", type=int, default=500)
    parser.add_argument("--ceiling", type=float, default=5.0)
    args = parser.parse_args()
    if args.cycles <= 0 or args.ceiling <= 0:
        raise SystemExit("cycles and ceiling must be positive")

    with tempfile.TemporaryDirectory(prefix="swir-shipping-bench-") as temporary:
        manifest = _fixture(Path(temporary) / "project")
        started = time.perf_counter()
        fingerprint = ""
        for _ in range(args.cycles):
            fingerprint = create_desktop_shipping_plan(manifest, "linux").fingerprint
        elapsed = time.perf_counter() - started

    print(
        f"desktop-shipping-1.9 cycles={args.cycles} elapsed={elapsed:.4f}s "
        f"fingerprint={fingerprint[:16]}"
    )
    if elapsed > args.ceiling:
        raise SystemExit(
            f"desktop shipping planning workload exceeded {args.ceiling:.2f}s ceiling: "
            f"{elapsed:.4f}s"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
