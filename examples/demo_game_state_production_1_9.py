from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from swirengine.game_state19 import ProductionGameStateSession, SaveProductionPolicy
from swirengine.shipping19 import GameSettings


def main() -> None:
    with TemporaryDirectory(prefix="swir-game-state-") as directory:
        root = Path(directory)
        policy = SaveProductionPolicy(
            autosave_keep=3,
            autosave_interval_seconds=30.0,
            max_manual_slots=8,
            max_workers=1,
        )
        with ProductionGameStateSession(
            "production-demo",
            user_data_root=root,
            policy=policy,
        ) as session:
            settings = session.settings_store()
            settings.save(
                GameSettings().with_accessibility(
                    reduced_motion=True,
                    subtitles=True,
                )
            )

            session.submit_manual(
                "campaign-1",
                {"scene": "warehouse", "health": 92, "inventory": ["keycard"]},
                metadata={"checkpoint": "loading-bay"},
            )
            session.submit_autosave(
                {"scene": "warehouse", "health": 92, "inventory": ["keycard"]},
                now=100.0,
                metadata={"checkpoint": "loading-bay"},
            )
            outcomes = session.run_until_idle(timeout=5.0)
            if not outcomes or not all(outcome.successful for outcome in outcomes):
                raise RuntimeError("production save demo did not complete successfully")

            manual = session.load("campaign-1")
            autosave = session.load_latest_autosave()
            if manual.data["scene"] != "warehouse" or autosave.data["health"] != 92:
                raise RuntimeError("production save demo roundtrip mismatch")

            print("SwirEngine 1.9 production game-state demo")
            print(f"user data: {session.location.root}")
            print(f"manual revision: {manual.revision}")
            print(f"autosave revision: {autosave.revision}")
            print(dict(session.diagnostics.portable()))


if __name__ == "__main__":
    main()
