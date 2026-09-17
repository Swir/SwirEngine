from __future__ import annotations

import time

from swirengine.render_graph18 import RenderGraphBuilder
from swirengine.render_resources18 import (
    RenderPlanPoolSession,
    RenderPlanResourceSchedule,
    RenderResourceDescriptor,
    TransientRenderResourcePool,
)

PASS_COUNT = 512
FRAMES = 100
SIZE_BYTES = 64 * 1024
BUDGET_SECONDS = 5.0


def build_plan():
    graph = RenderGraphBuilder(max_passes=PASS_COUNT + 8, max_resources=PASS_COUNT + 8)
    graph.add_resource("source", external=True)
    previous = "source"
    descriptors: dict[str, RenderResourceDescriptor] = {}
    for index in range(PASS_COUNT):
        name = f"stage-{index}"
        graph.add_resource(name, transient=True, size_bytes=SIZE_BYTES)
        graph.add_pass(f"pass-{index}", reads=(previous,), writes=(name,))
        descriptors[name] = RenderResourceDescriptor(
            "texture",
            "rgba8",
            128,
            128,
            usage="render-target",
            size_bytes=SIZE_BYTES,
        )
        previous = name
    graph.mark_output(previous)
    return graph.compile(), descriptors


def main() -> None:
    plan, descriptors = build_plan()
    schedule = RenderPlanResourceSchedule.from_plan(plan, descriptors)
    created: list[object] = []
    destroyed: list[object] = []

    def create(_descriptor: RenderResourceDescriptor) -> object:
        resource = object()
        created.append(resource)
        return resource

    def destroy(resource: object) -> None:
        destroyed.append(resource)

    pool = TransientRenderResourcePool(
        create=create,
        destroy=destroy,
        max_resources=8,
        max_bytes=8 * SIZE_BYTES,
    )
    started = time.perf_counter()
    try:
        for _ in range(FRAMES):
            session = RenderPlanPoolSession(pool, schedule)
            for pass_index in range(schedule.pass_count):
                session.begin_pass(pass_index)
                session.end_pass(pass_index)
        elapsed = time.perf_counter() - started
        diagnostics = pool.diagnostics()

        expected_acquires = PASS_COUNT * FRAMES
        if diagnostics.creates != 2:
            raise RuntimeError(
                f"linear render workload should stabilize at two physical allocations; "
                f"got {diagnostics.creates}"
            )
        if diagnostics.reuses != expected_acquires - diagnostics.creates:
            raise RuntimeError("transient pool reuse count changed unexpectedly")
        if diagnostics.leased_resources != 0:
            raise RuntimeError("render workload leaked active resource leases")
        if diagnostics.resident_resources != 2:
            raise RuntimeError("render workload retained an unexpected physical resource count")
        if elapsed > BUDGET_SECONDS:
            raise RuntimeError(
                f"transient resource workload exceeded {BUDGET_SECONDS:.1f}s budget: "
                f"{elapsed:.4f}s"
            )

        removed = pool.trim(target_resources=0, target_bytes=0)
        if removed != 2 or len(destroyed) != 2:
            raise RuntimeError("final trim did not destroy both idle physical resources")

        print(
            "render-resources-1.8 workload:",
            f"frames={FRAMES}",
            f"logical_acquires={expected_acquires}",
            f"physical_creates={diagnostics.creates}",
            f"reuses={diagnostics.reuses}",
            f"elapsed={elapsed:.4f}s",
        )
    finally:
        pool.close()


if __name__ == "__main__":
    main()
