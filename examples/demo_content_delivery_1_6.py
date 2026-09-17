from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from swirengine.content16 import (
    ContentStager,
    VerifiedContentCache,
    apply_patch,
    build_manifest,
    plan_patch,
)


def write(root: Path, relative: str, payload: bytes) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def main() -> None:
    with TemporaryDirectory(prefix="swirengine-content16-") as temporary:
        workspace = Path(temporary)
        installed = workspace / "installed"
        source = workspace / "source-v2"
        write(installed, "data/player.bin", b"player-v1")
        write(installed, "data/obsolete.bin", b"remove-me")
        write(source, "data/player.bin", b"player-v2")
        write(source, "data/map.bin", b"map-v2")

        current = build_manifest(installed, "demo-v1")
        target = build_manifest(source, "demo-v2", metadata={"channel": "local-demo"})
        patch = plan_patch(current, target)
        cache = VerifiedContentCache(workspace / "cache")
        stager = ContentStager(workspace / "stage")

        for relative in (*patch.additions, *patch.replacements):
            target_entry = target.entry_map()[relative]
            stager.stage_local_file(target_entry, source / relative, chunk_size=4)
            stager.finalize(target_entry, cache)

        report = apply_patch(patch, current, target, cache, installed)
        print(
            "content16 demo:",
            f"changed={patch.changed_files}",
            f"transfer_bytes={patch.transfer_bytes}",
            f"verified={report.ok}",
            f"manifest={target.fingerprint[:12]}",
        )
        if not report.ok:
            raise SystemExit("content verification failed")


if __name__ == "__main__":
    main()
