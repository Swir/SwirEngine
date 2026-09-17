from __future__ import annotations

from dataclasses import dataclass

from swirengine.render_graph18 import RenderGraphBuilder
from swirengine.render_resources18 import (
    RenderPlanPoolSession,
    RenderPlanResourceSchedule,
    RenderResourceDescriptor,
    TransientRenderResourcePool,
)


@dataclass(frozen=True)
class FakeGpuResource:
    resource_id: int
    descriptor: RenderResourceDescriptor


def main() -> None:
    graph = RenderGraphBuilder()
    graph.add_resource("camera", external=True)
    graph.add_resource("depth", transient=True, size_bytes=4 * 1024 * 1024)
    graph.add_resource("hdr", transient=True, size_bytes=8 * 1024 * 1024)
    graph.add_resource("post", transient=True, size_bytes=8 * 1024 * 1024)
    graph.add_resource("swapchain", external=True)
    graph.add_pass("depth-pass", reads=("camera",), writes=("depth",), priority=20)
    graph.add_pass("lighting-pass", reads=("depth",), writes=("hdr",), priority=10)
    graph.add_pass("post-pass", reads=("hdr",), writes=("post",))
    graph.add_pass("present-pass", reads=("post",), writes=("swapchain",), side_effect=True)
    plan = graph.compile()

    descriptors = {
        "depth": RenderResourceDescriptor(
            "texture",
            "depth24",
            1024,
            1024,
            usage="depth-attachment",
            size_bytes=4 * 1024 * 1024,
        ),
        "hdr": RenderResourceDescriptor(
            "texture",
            "rgba16f",
            1024,
            1024,
            usage="color-attachment",
            size_bytes=8 * 1024 * 1024,
        ),
        "post": RenderResourceDescriptor(
            "texture",
            "rgba16f",
            1024,
            1024,
            usage="color-attachment",
            size_bytes=8 * 1024 * 1024,
        ),
    }
    schedule = RenderPlanResourceSchedule.from_plan(plan, descriptors)
    created: list[FakeGpuResource] = []
    destroyed: list[int] = []

    def create(descriptor: RenderResourceDescriptor) -> FakeGpuResource:
        resource = FakeGpuResource(len(created), descriptor)
        created.append(resource)
        return resource

    def destroy(resource: FakeGpuResource) -> None:
        destroyed.append(resource.resource_id)

    pool = TransientRenderResourcePool(
        create=create,
        destroy=destroy,
        max_resources=8,
        max_bytes=32 * 1024 * 1024,
    )
    try:
        session = RenderPlanPoolSession(pool, schedule)
        for index, pass_name in enumerate(plan.passes):
            active = session.begin_pass(index)
            print(
                pass_name,
                {name: resource.resource_id for name, resource in active.items()},
            )
            session.end_pass(index)

        diagnostics = pool.diagnostics()
        print("render graph fingerprint:", plan.fingerprint)
        print("physical resources created:", diagnostics.creates)
        print("logical resource reuses:", diagnostics.reuses)
        print("resident bytes:", diagnostics.resident_bytes)
        print("portable diagnostics:", dict(diagnostics.portable()))
    finally:
        pool.close()

    print("destroyed backend resources:", destroyed)


if __name__ == "__main__":
    main()
