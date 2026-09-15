from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from swirengine.editor_systems import EditorSystemRegistry


@dataclass(slots=True)
class Diagnostics:
    active: int = 1
    visits: int = 0


def main() -> None:
    registry = EditorSystemRegistry()
    calls = [0] * 10_000

    for index in range(10_000):
        category = f"group-{index // 100}"

        def capture(slot: int = index) -> Diagnostics:
            calls[slot] += 1
            return Diagnostics(active=slot, visits=calls[slot])

        registry.register(
            f"system-{index:05d}",
            title=f"System {index:05d}",
            category=category,
            provider=capture,
        )

    started = perf_counter()
    frame = registry.frame(category="group-42")
    elapsed = perf_counter() - started

    provider_calls = sum(calls)
    if frame.total_systems != 10_000:
        raise SystemExit(f"expected 10000 registered systems, got {frame.total_systems}")
    if len(frame.systems) != 100:
        raise SystemExit(f"expected 100 selected systems, got {len(frame.systems)}")
    if provider_calls != 100:
        raise SystemExit(f"filtered capture must call exactly 100 providers, got {provider_calls}")

    print("Editor systems benchmark (host timing diagnostic only)")
    print(f"registered_systems={frame.total_systems}")
    print(f"selected_systems={len(frame.systems)}")
    print(f"provider_calls={provider_calls}")
    print(f"elapsed_seconds={elapsed:.6f}")
    print("No FPS uplift is claimed from this host-dependent timing.")


if __name__ == "__main__":
    main()
