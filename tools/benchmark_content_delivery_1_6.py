from __future__ import annotations

import hashlib
from time import perf_counter

from swirengine.content16 import ContentEntry, ContentManifest, plan_patch

ENTRY_COUNT = 10_000
BUDGET_SECONDS = 4.0


def make_entry(index: int, revision: int) -> ContentEntry:
    payload = f"asset:{index}:revision:{revision}".encode()
    return ContentEntry(
        f"content/{index // 100:03d}/asset-{index:05d}.bin",
        hashlib.sha256(payload).hexdigest(),
        len(payload),
    )


def main() -> None:
    started = perf_counter()
    current_entries = [make_entry(index, 1) for index in range(ENTRY_COUNT)]
    target_entries = [
        make_entry(index, 2 if index % 7 == 0 else 1)
        for index in range(250, ENTRY_COUNT)
    ]
    target_entries.extend(make_entry(ENTRY_COUNT + index, 1) for index in range(250))
    current = ContentManifest.create("bench-v1", current_entries)
    target = ContentManifest.create("bench-v2", target_entries)
    plan = plan_patch(current, target)
    manifest_payload = target.to_json()
    parsed = ContentManifest.parse_json(manifest_payload)
    elapsed = perf_counter() - started

    assert parsed.fingerprint == target.fingerprint
    assert plan.changed_files > 1_000
    print(
        f"content16 workload: entries={ENTRY_COUNT} changed={plan.changed_files} "
        f"json_bytes={len(manifest_payload)} elapsed={elapsed:.4f}s "
        f"budget={BUDGET_SECONDS:.1f}s"
    )
    if elapsed >= BUDGET_SECONDS:
        raise SystemExit("content16 deterministic workload exceeded its CI budget")


if __name__ == "__main__":
    main()
