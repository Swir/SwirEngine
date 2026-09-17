from __future__ import annotations

from swirengine.render_graph18 import RenderGraphBuilder


def main() -> None:
    graph = RenderGraphBuilder()
    graph.add_resource("camera", external=True)
    graph.add_resource("shadow", transient=True, size_bytes=8 * 1024 * 1024)
    graph.add_resource("hdr", transient=True, size_bytes=16 * 1024 * 1024)
    graph.add_resource("bloom", transient=True, size_bytes=8 * 1024 * 1024)
    graph.add_resource("swapchain", external=True)

    graph.add_pass("shadow-pass", reads=("camera",), writes=("shadow",), priority=20)
    graph.add_pass(
        "lighting-pass",
        reads=("camera", "shadow"),
        writes=("hdr",),
        priority=10,
    )
    graph.add_pass("bloom-pass", reads=("hdr",), writes=("bloom",))
    graph.add_pass(
        "present-pass",
        reads=("bloom",),
        writes=("swapchain",),
        side_effect=True,
    )

    plan = graph.compile()
    print("SwirEngine 1.8 render graph")
    print("pass order:", " -> ".join(plan.passes))
    print("alias slots:", plan.diagnostics.alias_slots)
    print("transient peak bytes:", plan.diagnostics.transient_peak_live_bytes)
    print("fingerprint:", plan.fingerprint)


if __name__ == "__main__":
    main()
