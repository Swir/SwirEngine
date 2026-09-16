from __future__ import annotations

import tempfile
from pathlib import Path

from swirengine.storage15 import AutosavePolicy, ProfileSaveManager2


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        manager = ProfileSaveManager2(Path(directory), "demo-player")
        manager.save(
            "manual-1",
            {"level": 4, "score": 1200, "player": {"health": 85}},
            metadata={"title": "Before the boss"},
        )
        manager.save(
            "manual-1",
            {"level": 4, "score": 1350, "player": {"health": 70}},
            metadata={"title": "Boss arena"},
        )

        policy = AutosavePolicy(keep=3)
        for tick in range(1, 6):
            manager.autosave(
                {"tick": tick, "position": [tick * 2, 0, tick * -3]},
                policy=policy,
                metadata={"scene": "demo-arena"},
            )

        manual = manager.load("manual-1")
        autosaves = manager.list_autosaves(policy=policy)
        latest = manager.load(autosaves[0].name)

        if manual.revision != 2 or manual.data["score"] != 1350:
            raise AssertionError("manual save revision did not round-trip")
        if latest.data["tick"] != 5:
            raise AssertionError("autosave rotation did not retain the latest generation")
        if len(autosaves) != 3:
            raise AssertionError("autosave rotation exceeded its retention policy")

        print("SwirEngine 1.5 Save & Profile 2.0 demo")
        print(f"manual revision: {manual.revision}")
        print(f"manual backup: {manager.slot('manual-1').backup_path.exists()}")
        print(
            "autosave generations:",
            [item.metadata["autosave_generation"] for item in autosaves if item.metadata],
        )
        print(f"latest autosave tick: {latest.data['tick']}")


if __name__ == "__main__":
    main()
