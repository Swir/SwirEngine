from __future__ import annotations

import hashlib

from swirengine.jobs17 import JobScheduler, JobState


def hash_asset(context, payload: bytes) -> str:
    context.raise_if_cancelled()
    return hashlib.sha256(payload).hexdigest()


def main() -> None:
    payloads = {
        "terrain": b"terrain-source-bytes",
        "audio": b"audio-source-bytes",
        "ui": b"ui-source-bytes",
    }

    with JobScheduler(max_workers=3, max_pending=16) as scheduler:
        for name, payload in payloads.items():
            scheduler.submit(
                f"hash:{name}",
                lambda context, current=payload: hash_asset(context, current),
                priority=5 if name == "ui" else 0,
            )
        scheduler.submit(
            "manifest-ready",
            lambda context: "all source hashes are ready for main-thread commit",
            dependencies=[f"hash:{name}" for name in payloads],
        )
        scheduler.wait_all(timeout=2.0)

        for outcome in scheduler.drain_completed():
            if outcome.state is JobState.SUCCEEDED:
                print(f"{outcome.job_id}: {outcome.value}")
            else:
                print(f"{outcome.job_id}: {outcome.state.value} ({outcome.error_type})")

        print(scheduler.diagnostics().portable())


if __name__ == "__main__":
    main()
