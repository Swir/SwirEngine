from __future__ import annotations

import time

from swirengine.work_graph17 import StreamingWorkGraph, WorkPhase

CHAINS = 512
BUDGET_SECONDS = 5.0


def main() -> None:
    graph = StreamingWorkGraph(
        max_nodes=CHAINS * 4,
        max_workers=4,
        max_pending_background=CHAINS * 2 + 32,
        max_background_submissions_per_poll=128,
    )

    for index in range(CHAINS):
        prefetch = f"prefetch:{index}"
        decode = f"decode:{index}"
        instantiate = f"instantiate:{index}"
        unload = f"unload:{index}"
        graph.add(prefetch, WorkPhase.PREFETCH, lambda _ctx, value=index: value)
        graph.add(
            decode,
            WorkPhase.DECODE,
            lambda ctx, source=prefetch: int(ctx.dependency_values[source]) + 1,
            dependencies=[prefetch],
        )
        graph.add(
            instantiate,
            WorkPhase.INSTANTIATE,
            lambda ctx, source=decode: int(ctx.dependency_values[source]) * 2,
            dependencies=[decode],
        )
        graph.add(
            unload,
            WorkPhase.UNLOAD,
            lambda ctx, source=instantiate: int(ctx.dependency_values[source]),
            dependencies=[instantiate],
        )

    started = time.perf_counter()
    try:
        results = graph.run_until_complete(max_items=128, timeout=BUDGET_SECONDS)
    finally:
        graph.shutdown(wait=True, cancel_pending=True)
    elapsed = time.perf_counter() - started

    if len(results) != CHAINS * 4 or not all(result.successful for result in results):
        raise SystemExit("streaming work graph workload did not complete successfully")
    if elapsed > BUDGET_SECONDS:
        raise SystemExit(
            f"streaming work graph workload exceeded {BUDGET_SECONDS:.1f}s: {elapsed:.4f}s"
        )

    print(
        "Streaming Work Graph 3.0 workload: "
        f"{CHAINS * 4} nodes across {CHAINS} four-stage chains in {elapsed:.4f}s; "
        f"budget {BUDGET_SECONDS:.1f}s"
    )


if __name__ == "__main__":
    main()
