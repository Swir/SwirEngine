from __future__ import annotations

import tempfile
import time
from pathlib import Path

from swirengine.storage15 import AutosavePolicy, ProfileSaveManager2

SAVE_COUNT = 250
MAX_SECONDS = 5.0


def main() -> None:
    payload = {
        "player": {"name": "benchmark", "health": 100},
        "inventory": [f"item-{index}" for index in range(128)],
        "world": {f"flag-{index}": index % 3 == 0 for index in range(128)},
    }
    policy = AutosavePolicy(keep=5)

    with tempfile.TemporaryDirectory() as directory:
        manager = ProfileSaveManager2(Path(directory), "benchmark")
        started = time.perf_counter()
        for generation in range(1, SAVE_COUNT + 1):
            frame = dict(payload)
            frame["tick"] = generation
            manager.autosave(frame, policy=policy)

        autosaves = manager.list_autosaves(policy=policy)
        latest = autosaves[0]
        loaded = manager.load(latest.name)
        elapsed = time.perf_counter() - started

        if len(autosaves) != policy.keep:
            raise AssertionError(f"expected {policy.keep} autosaves, got {len(autosaves)}")
        if loaded.data["tick"] != SAVE_COUNT:
            raise AssertionError("latest autosave does not contain the final generation")
        if not all(item.healthy for item in autosaves):
            raise AssertionError("autosave benchmark produced an unhealthy slot")
        if elapsed > MAX_SECONDS:
            raise AssertionError(
                f"save/profile workload exceeded {MAX_SECONDS:.1f}s: {elapsed:.6f}s"
            )

        bytes_on_disk = sum(path.stat().st_size for path in manager.directory.iterdir())
        print(
            "save-profile-2-1.5",
            f"writes={SAVE_COUNT}",
            f"retained={len(autosaves)}",
            f"bytes={bytes_on_disk}",
            f"elapsed={elapsed:.6f}s",
        )


if __name__ == "__main__":
    main()
