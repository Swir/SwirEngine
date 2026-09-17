from __future__ import annotations

from tempfile import TemporaryDirectory

from swirengine.background_save17 import BackgroundSavePipeline
from swirengine.storage15 import ProfileSaveManager2


def main() -> None:
    with TemporaryDirectory(prefix="swirengine-save-demo-") as temporary:
        manager = ProfileSaveManager2(temporary, "demo")
        live_state = {
            "player": {"hp": 100, "position": [12.0, 4.0, -3.0]},
            "inventory": ["keycard", "battery"],
        }

        with BackgroundSavePipeline(max_workers=2) as saves:
            saves.submit_profile(
                "checkpoint-1",
                manager,
                "campaign",
                lambda: live_state,
                metadata={"reason": "checkpoint"},
            )
            # This happens after the immutable snapshot was captured.
            live_state["player"]["hp"] = 25

            outcome = saves.run_until_idle()[0]
            loaded = manager.load("campaign")

            print(
                "background_save",
                {
                    "state": outcome.state.value,
                    "revision": outcome.receipt.revision if outcome.receipt else None,
                    "saved_hp": loaded.data["player"]["hp"],
                    "live_hp": live_state["player"]["hp"],
                    "diagnostics": dict(saves.diagnostics().portable()),
                },
            )


if __name__ == "__main__":
    main()
