from __future__ import annotations

import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from swirengine.assets import AssetManager  # noqa: E402
from swirengine.assets17 import AsyncAssetPipeline  # noqa: E402


def main() -> int:
    main_thread = threading.get_ident()
    with tempfile.TemporaryDirectory(prefix="swirengine-assets17-demo-") as temporary:
        root = Path(temporary)
        (root / "ship.mesh").write_text("1,2,3,5,8", encoding="utf-8")

        pipeline = AsyncAssetPipeline(AssetManager(root), max_workers=2, max_pending=32)

        def decode(path: Path, context) -> tuple[int, ...]:
            assert threading.get_ident() != main_thread
            context.raise_if_cancelled()
            return tuple(int(item) for item in path.read_text().split(","))

        def cook(values: tuple[int, ...], context) -> dict[str, object]:
            context.raise_if_cancelled()
            return {"vertices": values, "vertex_count": len(values)}

        def finalize(cooked: dict[str, object]) -> dict[str, object]:
            assert threading.get_ident() == main_thread
            return {**cooked, "uploaded_on_main_thread": True}

        pipeline.register_processor(
            "mesh",
            suffixes=[".mesh"],
            decode=decode,
            cook=cook,
            finalizer=finalize,
        )

        request = pipeline.submit("ship.mesh", priority=10)
        pipeline.wait_workers(timeout=2.0)
        result = pipeline.poll(max_items=1)[0]
        diagnostics = pipeline.diagnostics()
        pipeline.shutdown(wait=True, cancel_pending=True)

    assert result.request_id == request.request_id
    assert result.successful
    assert result.value == {
        "vertices": (1, 2, 3, 5, 8),
        "vertex_count": 5,
        "uploaded_on_main_thread": True,
    }
    print("Async Asset Decode/Cook 1.7 demo complete")
    print(f"worker_ms={result.worker_ms:.3f}")
    print(f"diagnostics={dict(diagnostics.portable())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
