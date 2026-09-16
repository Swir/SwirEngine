from __future__ import annotations

import tempfile
from pathlib import Path
from time import perf_counter

from swirengine.audio15 import AudioEngine2, AudioSnapshot

OPERATIONS = 5_000
MAX_SECONDS = 5.0


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="swirengine-audio2-bench-") as directory:
        root = Path(directory)
        tone = root / "tone.wav"
        tone.write_bytes(b"swirengine-audio2-benchmark")

        audio = AudioEngine2.headless(root, max_voices=32)
        snapshot = AudioSnapshot.from_mapping(
            "combat",
            {
                "sfx": {"volume": 0.8, "muted": False},
                "dialogue": {"volume": 0.7, "muted": False},
            },
            master_volume=0.9,
        )

        started = perf_counter()
        for index in range(OPERATIONS):
            priority = 255 if index >= 32 else index
            voice = audio.play(
                "tone.wav",
                priority=priority,
                bus="dialogue" if index % 4 == 0 else "sfx",
                pan=((index % 21) - 10) / 10.0,
                position=(float(index % 9), 0.0, float(index % 7)),
                max_distance=32.0,
            )
            if index % 50 == 0:
                audio.apply_snapshot(snapshot, duration=0.05)
            audio.update(1.0 / 120.0)
            if voice is not None and index % 17 == 0:
                voice.stop()

        elapsed = perf_counter() - started
        diagnostics = audio.diagnostics()
        fingerprint = audio.state_fingerprint()

        if diagnostics.active_voices > diagnostics.max_voices:
            raise SystemExit(
                f"voice budget violated: {diagnostics.active_voices} > {diagnostics.max_voices}"
            )
        if diagnostics.stolen_voices == 0:
            raise SystemExit("benchmark did not exercise priority voice stealing")
        if len(fingerprint) != 64:
            raise SystemExit("unexpected Audio 2.0 state fingerprint")
        if elapsed > MAX_SECONDS:
            raise SystemExit(
                f"Audio 2.0 workload exceeded {MAX_SECONDS:.1f}s contract: {elapsed:.6f}s"
            )

        print(
            "audio-2-1.5 "
            f"operations={OPERATIONS} elapsed={elapsed:.6f}s "
            f"active={diagnostics.active_voices} "
            f"stolen={diagnostics.stolen_voices} "
            f"rejected={diagnostics.rejected_voices} "
            f"fingerprint={fingerprint}"
        )
        audio.shutdown()


if __name__ == "__main__":
    main()
