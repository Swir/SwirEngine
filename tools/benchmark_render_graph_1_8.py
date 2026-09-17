from __future__ import annotations

import time

from swirengine.render_graph18 import RenderGraphBuilder

PASS_COUNT = 1200
BUDGET_SECONDS = 5.0


def build_workload() -> RenderGraphBuilder:
    graph = RenderGraphBuilder(max_passes=PASS_COUNT + 8, max_resources=PASS_COUNT + 8)
    graph.add_resource("source", external=True)
    previous = "source"
    for index in range(PASS_COUNT):
        output = f"stage-{index}"
        graph.add_resource(output, transient=True, size_bytes=64 * 1024 + (index % 17) * 4096)
        graph.add_pass(
            f"pass-{index}",
            reads=(previous,),
            writes=(output,),
            priority=index % 5,
        )
        previous = output
    graph.mark_output(previous)
    return graph


def main() -> None:
    graph = build_workload()
    start = time.perf_counter()
    plan = graph.compile()
    elapsed = time.perf_counter() - start

    if len(plan.passes) != PASS_COUNT:
        raise RuntimeError(f"expected {PASS_COUNT} active passes, got {len(plan.passes)}")
    if plan.diagnostics.alias_slots > 2:
        raise RuntimeError(
            "linear workload should need at most two transient alias slots; "
            f"got {plan.diagnostics.alias_slots}"
        )
    if elapsed > BUDGET_SECONDS:
        raise RuntimeError(
            f"render graph workload exceeded {BUDGET_SECONDS:.1f}s budget: {elapsed:.4f}s"
        )

    print(
        "render-graph-1.8 workload:",
        f"passes={len(plan.passes)}",
        f"resources={plan.diagnostics.active_resources}",
        f"alias_slots={plan.diagnostics.alias_slots}",
        f"elapsed={elapsed:.4f}s",
    )


if __name__ == "__main__":
    main()
