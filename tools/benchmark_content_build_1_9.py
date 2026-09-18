from __future__ import annotations

import argparse
import tempfile
from pathlib import Path
from time import perf_counter

from swirengine.content_build19 import ContentBuildGraph
from swirengine.project19 import ProjectManifest


def _write_fixture(root: Path, node_count: int) -> ProjectManifest:
    (root / "main.py").write_text("print('benchmark')\n", encoding="utf-8")
    (root / "content").mkdir()
    manifest = [
        'name = "Content Build Benchmark"',
        'mode = "3d"',
        'entrypoint = "main.py"',
        "",
        "[content]",
        'include = ["content"]',
    ]
    for index in range(node_count):
        path = root / "content" / f"node-{index:04d}.bin"
        path.write_bytes(bytes((index % 251,)) * 16)
        kind = ("shader", "asset", "generated", "scene")[index % 4]
        load = ("warmup", "preload", "preload", "stream")[index % 4]
        manifest.extend(
            [
                "",
                "[[content.build.nodes]]",
                f'name = "node:{index:04d}"',
                f'kind = "{kind}"',
                f'path = "content/node-{index:04d}.bin"',
                f'load = "{load}"',
            ]
        )
        if index:
            manifest.append(f'depends_on = ["node:{index - 1:04d}"]')
    (root / "swirproject.toml").write_text("\n".join(manifest) + "\n", encoding="utf-8")
    return ProjectManifest.load(root)


def run_workload(*, node_count: int, iterations: int) -> tuple[float, str]:
    with tempfile.TemporaryDirectory(prefix="swir-content-build-") as directory:
        root = Path(directory)
        manifest = _write_fixture(root, node_count)
        graph = ContentBuildGraph.load_optional(manifest)
        if graph is None:
            raise RuntimeError("benchmark fixture did not produce a content build graph")
        if graph.diagnostics():
            raise RuntimeError(f"benchmark fixture diagnostics: {graph.diagnostics()!r}")
        target = f"node:{node_count - 1:04d}"
        expected = graph.plan([target]).fingerprint
        started = perf_counter()
        for _ in range(iterations):
            plan = graph.plan([target])
            if plan.fingerprint != expected or len(plan.ordered_nodes) != node_count:
                raise RuntimeError("content build plan changed during deterministic workload")
        elapsed = perf_counter() - started
        return elapsed, expected


def main() -> int:
    parser = argparse.ArgumentParser(description="SwirEngine 1.9 content-build regression workload")
    parser.add_argument("--nodes", type=int, default=256)
    parser.add_argument("--iterations", type=int, default=2500)
    parser.add_argument("--max-seconds", type=float, default=8.0)
    args = parser.parse_args()
    if args.nodes < 1 or args.nodes > 1024:
        parser.error("--nodes must be between 1 and 1024")
    if args.iterations < 1:
        parser.error("--iterations must be >= 1")
    if args.max_seconds <= 0:
        parser.error("--max-seconds must be > 0")

    elapsed, fingerprint = run_workload(node_count=args.nodes, iterations=args.iterations)
    plans_per_second = args.iterations / elapsed if elapsed else float("inf")
    print(
        f"content-build workload: nodes={args.nodes} iterations={args.iterations} "
        f"elapsed={elapsed:.4f}s plans/s={plans_per_second:.1f} "
        f"fingerprint={fingerprint[:16]}"
    )
    if elapsed > args.max_seconds:
        print(f"FAIL: workload exceeded {args.max_seconds:.2f}s budget")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
