from __future__ import annotations

from dataclasses import dataclass

from swirengine.performance15 import PerformanceDiagnostics2


@dataclass(frozen=True)
class NavigationDiagnostics:
    active_agents: int
    visited_nodes: int


@dataclass(frozen=True)
class StreamingDiagnostics:
    active_cells: int
    queued_cells: int


def main() -> None:
    perf = PerformanceDiagnostics2(history=4)
    navigation = NavigationDiagnostics(active_agents=12, visited_nodes=48)
    streaming = StreamingDiagnostics(active_cells=9, queued_cells=2)

    perf.bind_provider("navigation", lambda: navigation)
    perf.bind_provider("streaming", lambda: streaming)

    for index in range(3):
        perf.begin_frame()
        perf.record_timing("frame", "update", 0.002 + index * 0.0001)
        perf.record_timing("frame", "physics", 0.001)
        perf.record_timing("frame", "render", 0.004)
        perf.record_timing("asset", "characters/hero.glb", 0.0005)
        perf.record_resource("scene_objects", count=180 + index)
        perf.record_resource("textures", count=24, bytes_used=64 * 1024 * 1024)
        perf.end_frame(1.0 / 60.0)

    latest = perf.latest
    assert latest is not None
    capture = perf.capture({"scenario": "headless-demo", "seed": 7})

    print(
        f"frame={latest.index} frame_ms={latest.frame_ms:.3f} "
        f"update_ms={latest.update_ms:.3f} render_ms={latest.render_ms:.3f}"
    )
    print(
        f"frames={len(capture.frames)} fingerprint={capture.fingerprint[:16]} "
        f"provider_errors={perf.provider_errors}"
    )


if __name__ == "__main__":
    main()
