from __future__ import annotations

import time

from swirengine.shipping19 import GameSettings, ProductionActionMap


def main() -> int:
    action_payload = ProductionActionMap.standard().to_dict()
    settings_payload = GameSettings().to_dict()
    iterations = 5_000

    started = time.perf_counter()
    digest = ""
    for index in range(iterations):
        actions = ProductionActionMap.from_dict(action_payload)
        settings = GameSettings.from_dict(settings_payload)
        digest = actions.fingerprint if index % 2 == 0 else settings.fingerprint
    elapsed = time.perf_counter() - started

    if not digest:
        raise RuntimeError("production settings workload produced no fingerprint")
    ceiling = 5.0
    print(
        "input/ui/settings workload: "
        f"{iterations:,} profile/settings cycles in {elapsed:.4f}s "
        f"(ceiling {ceiling:.1f}s)"
    )
    if elapsed >= ceiling:
        raise RuntimeError(
            f"input/ui/settings workload exceeded {ceiling:.1f}s ceiling: {elapsed:.4f}s"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
