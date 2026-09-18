from __future__ import annotations

import time
from pathlib import Path
from tempfile import TemporaryDirectory

from swirengine.game_state19 import ProductionGameStateSession, SaveProductionPolicy


def main() -> None:
    with TemporaryDirectory(prefix="swir-game-state-bench-") as directory:
        policy = SaveProductionPolicy(
            autosave_keep=4,
            autosave_interval_seconds=0.0,
            max_manual_slots=32,
            max_background_requests=32,
            max_workers=2,
        )
        started = time.perf_counter()
        with ProductionGameStateSession(
            "game-state-workload",
            user_data_root=Path(directory),
            policy=policy,
        ) as session:
            for index in range(24):
                session.submit_manual(
                    f"slot-{index:02d}",
                    {
                        "frame": index * 120,
                        "position": [index * 0.5, 1.0, -index * 0.25],
                        "inventory": ["tool", f"item-{index:02d}"],
                    },
                    metadata={"workload": True},
                )
            outcomes = session.run_until_idle(timeout=10.0)
            if len(outcomes) != 24 or not all(outcome.successful for outcome in outcomes):
                raise RuntimeError("manual-save workload failed")

            for index in range(8):
                request = session.submit_autosave(
                    {"frame": 10_000 + index, "checkpoint": index},
                    now=float(index),
                    force=True,
                )
                if request is None:
                    raise RuntimeError("forced autosave was unexpectedly skipped")
                completed = session.run_until_idle(timeout=10.0)
                if not completed or not completed[-1].successful:
                    raise RuntimeError("autosave workload failed")

            latest = session.load_latest_autosave()
            if latest.data["checkpoint"] != 7:
                raise RuntimeError("latest autosave workload result mismatch")

            elapsed = time.perf_counter() - started
            diagnostics = session.diagnostics
            if diagnostics.pipeline.verified_writes_total != 32:
                raise RuntimeError("verified-write workload count mismatch")
            if elapsed > 10.0:
                raise RuntimeError(
                    f"production game-state workload exceeded 10.0s ceiling: {elapsed:.4f}s"
                )
            print(
                "game-state production workload: "
                f"32 verified writes + recovery read in {elapsed:.4f}s"
            )


if __name__ == "__main__":
    main()
