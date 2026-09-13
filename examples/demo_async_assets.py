from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from time import sleep

from swirengine.assets import AssetManager
from swirengine.asset_pipeline import AssetPreloader


with TemporaryDirectory(prefix="swir-assets-") as temp_dir:
    root = Path(temp_dir)
    for index in range(6):
        (root / f"chunk-{index}.txt").write_text(f"level chunk {index}", encoding="utf-8")

    assets = AssetManager(root)

    def decode(path: Path) -> str:
        sleep(0.02)  # stand-in for parsing/decompression work
        return path.read_text(encoding="utf-8").upper()

    assets.register_loader("txt", decode)

    with AssetPreloader(assets, max_workers=3) as preloader:
        future = preloader.preload_async([f"chunk-{index}.txt" for index in range(6)])
        print("Loading screen can keep updating while assets decode...")
        report = future.result()

    print(f"loaded={report.loaded}/{report.total}, failed={report.failed}")
    print(f"wall={report.wall_time_ms:.2f} ms, avoided-wait={report.stall_reduction_ratio:.1%}")
