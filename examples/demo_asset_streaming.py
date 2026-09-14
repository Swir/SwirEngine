from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from time import sleep

from swirengine.asset_streaming import AssetStreamingBudget, AssetStreamingManager
from swirengine.assets import AssetManager


def main() -> None:
    with TemporaryDirectory(prefix="swir-streaming-") as temp_dir:
        root = Path(temp_dir)
        for index in range(6):
            (root / f"chunk-{index}.txt").write_text("x" * (index + 1) * 32, encoding="utf-8")

        assets = AssetManager(root)
        assets.register_loader("txt", lambda path: path.read_text(encoding="utf-8"))
        budget = AssetStreamingBudget(max_resident_bytes=320, max_resident_assets=3)

        with AssetStreamingManager(assets, budget=budget) as streaming:
            streaming.stage("chunk-0.txt", pin=True)
            streaming.stage_many(f"chunk-{index}.txt" for index in range(1, 6))

            while streaming.diagnostics().pending:
                for result in streaming.pump(max_completions=2):
                    print(f"ready: {result.path.name} ({result.duration_ms:.3f} ms worker time)")
                sleep(0.005)

            print("resident:", [item.path.name for item in streaming.resident()])
            print("diagnostics:", streaming.diagnostics())


if __name__ == "__main__":
    main()
