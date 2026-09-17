from __future__ import annotations

from swirengine.work_graph17 import StreamingWorkGraph, WorkPhase


def main() -> None:
    graph = StreamingWorkGraph(max_workers=2, max_nodes=16)
    graph.add("prefetch:town", WorkPhase.PREFETCH, lambda _ctx: b"town-chunk")
    graph.add(
        "decode:town",
        WorkPhase.DECODE,
        lambda ctx: ctx.dependency_values["prefetch:town"].decode("utf-8").upper(),
        dependencies=["prefetch:town"],
    )
    graph.add(
        "instantiate:town",
        WorkPhase.INSTANTIATE,
        lambda ctx: {"scene": ctx.dependency_values["decode:town"], "mounted": True},
        dependencies=["decode:town"],
    )
    graph.add(
        "unload:town",
        WorkPhase.UNLOAD,
        lambda ctx: f"unloaded:{ctx.dependency_values['instantiate:town']['scene']}",
        dependencies=["instantiate:town"],
    )

    try:
        results = graph.run_until_complete(max_items=4, timeout=2.0)
        print("Streaming Work Graph 3.0 demo complete")
        print(f"final={results[-1].value}")
        print(f"diagnostics={dict(graph.diagnostics().portable())}")
    finally:
        graph.shutdown(wait=True, cancel_pending=True)


if __name__ == "__main__":
    main()
