from __future__ import annotations

from swirengine.performance15 import PerformanceDiagnostics2
from swirengine.render_graph18 import RenderGraphBuilder
from swirengine.render_timing18 import GpuTimingRecorder


class DemoTimingProvider:
    def __init__(self) -> None:
        self.values = {
            "shadow": 0.0016,
            "lighting": 0.0028,
            "present": 0.0004,
        }

    def begin(self, frame_index: int, pass_name: str) -> object | None:
        return frame_index, pass_name

    def end(self, token: object) -> None:
        return None

    def poll(self, token: object) -> float | None:
        _frame, pass_name = token
        return self.values[str(pass_name)]


def build_plan():
    graph = RenderGraphBuilder()
    graph.add_resource("camera", external=True)
    graph.add_resource("shadow-map", transient=True, size_bytes=4 * 1024 * 1024)
    graph.add_resource("hdr", transient=True, size_bytes=8 * 1024 * 1024)
    graph.add_resource("backbuffer", external=True)
    graph.add_pass("shadow", reads=("camera",), writes=("shadow-map",))
    graph.add_pass(
        "lighting",
        reads=("camera", "shadow-map"),
        writes=("hdr",),
    )
    graph.add_pass(
        "present",
        reads=("hdr",),
        writes=("backbuffer",),
        side_effect=True,
    )
    return graph.compile()


def main() -> None:
    plan = build_plan()
    recorder = GpuTimingRecorder(DemoTimingProvider())

    recorder.begin_frame(plan)
    for pass_name in plan.passes:
        recorder.begin_pass(pass_name)
        # Real backends submit that pass's GPU commands here.
        recorder.end_pass()
    recorder.end_frame()
    frame = recorder.poll_ready()[0]

    performance = PerformanceDiagnostics2()
    performance.begin_frame()
    recorder.record_into(performance, frame)
    diagnostics_frame = performance.end_frame(frame_seconds=1.0 / 60.0)

    capture = recorder.capture({"scene": "gpu-timing-demo", "backend": "synthetic"})
    print("GPU frame ms:", f"{frame.gpu_ms:.3f}")
    print("Performance timings:", len(diagnostics_frame.timings))
    print(
        "Hotspots:",
        ", ".join(
            f"{item.pass_name}={item.average_ms:.3f}ms"
            for item in capture.hotspots()
        ),
    )
    print("Capture fingerprint:", capture.fingerprint)


if __name__ == "__main__":
    main()
