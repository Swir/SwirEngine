# Save & Profile 2.0 — SwirEngine 1.5

SwirEngine 1.5 adds an opt-in save/profile layer in `swirengine.storage15`. It is intentionally separate from the stable 1.x `SaveStore`, `SettingsStore` and `ProfileStore` formats, so existing projects and save files continue to work unchanged.

## Why a second save layer?

The stable `SaveStore` is deliberately small: one plain JSON object written atomically. Save & Profile 2.0 targets longer-lived game projects that need stronger recovery and migration contracts without breaking that simple API.

The new layer adds:

- versioned save-slot envelopes;
- SHA-256 integrity records over canonical portable state;
- atomic writes with a last-known-good backup;
- automatic fallback to a valid backup when the primary is unreadable;
- explicit repair/recovery;
- ordered data migrations using the existing `MigrationRegistry`;
- caller-defined slot metadata and revision numbers;
- a profile manager isolated under `profiles/<profile>/saves-v2`;
- bounded autosave rotation with monotonic recoverable generations;
- legacy 1.x slot import without modifying the original file;
- health/recovery inspection for save-selection UIs and diagnostics.

## Manual save

```python
from swirengine.storage15 import ProfileSaveManager2

manager = ProfileSaveManager2("game-data", "player-1")
manager.save(
    "manual-1",
    {"level": 4, "score": 1200},
    metadata={"title": "Before the boss"},
)

loaded = manager.load("manual-1")
print(loaded.data)
print(loaded.revision)
```

A second successful save to the same slot first preserves the previous verified primary as `<slot>.json.bak`, then atomically replaces the primary. A corrupt primary is never silently used as a backup.

## Integrity and recovery

Every envelope contains a SHA-256 digest of the canonical envelope body. The digest is an accidental-corruption/divergence detector, not an authentication or anti-cheat mechanism.

`SaveSlotStore2.load()` follows this policy:

1. verify and load the primary;
2. if primary parsing, format, version or integrity validation fails, verify the backup;
3. return the backup with `result.source == "backup"` when it is valid;
4. raise `SaveRecoveryError` when neither copy can be trusted.

Use `load(repair=True)` or `recover()` to copy the verified backup back to the primary path. When saving, an unreadable primary is restored from a valid backup before the new revision is written. If both copies are unreadable, the save operation stops instead of destroying evidence or the only remaining data.

## Portable data contract

Save data and metadata accept JSON-shaped values:

- `None`;
- booleans;
- strings;
- integers;
- finite floats;
- lists/tuples;
- mappings with string keys.

Non-finite floats and arbitrary Python objects are rejected. `-0.0` is canonicalized to `0.0` before hashing.

## Version migrations

Save versions are project-defined integers starting at 1. The existing `swirengine.storage.MigrationRegistry` is reused so settings and save migration policy stay conceptually aligned.

```python
from swirengine.storage import MigrationRegistry
from swirengine.storage15 import SaveSlotStore2

migrations = MigrationRegistry()
migrations.register(1, lambda data: {"coins": data.pop("credits"), **data})

slot = SaveSlotStore2("slot.json", version=2, migrations=migrations)
result = slot.load()
```

Loading migrates in memory. `load(upgrade=True)` also writes the migrated state back as a new revision, while keeping the previous envelope as the backup.

A file newer than the supported project save version is rejected instead of being guessed or downgraded.

## Autosave retention

`ProfileSaveManager2.autosave()` uses an `AutosavePolicy` rather than one ever-growing file:

```python
from swirengine.storage15 import AutosavePolicy, ProfileSaveManager2

manager = ProfileSaveManager2("game-data")
policy = AutosavePolicy(keep=3, prefix="autosave")

manager.autosave({"checkpoint": 1}, policy=policy)
manager.autosave({"checkpoint": 2}, policy=policy)
manager.autosave({"checkpoint": 3}, policy=policy)
manager.autosave({"checkpoint": 4}, policy=policy)
```

The manager retains three primary autosave slots and orders `list_autosaves()` by the newest recoverable `autosave_generation`. Each slot still has its own last-known-good backup when it has been overwritten at least once.

## Legacy import

Save & Profile 2.0 does not reinterpret legacy files in place. `import_legacy(slot)` reads the matching stable 1.x `ProfileStore` slot and creates a new versioned copy in `saves-v2`. The original `profiles/<profile>/saves/<slot>.json` remains unchanged.

## Slot inspection

`SaveSlotStore2.inspect()` and `ProfileSaveManager2.list_slots()` expose:

- healthy/unhealthy primary status;
- whether a verified backup can recover the slot;
- save version;
- revision;
- metadata.

This lets game save menus show a recoverable/corrupt state without loading game data into the active runtime.

## Compatibility

This milestone does not change `swirengine.__init__`, `SaveStore`, `SettingsStore`, `ProfileStore`, or any stable 1.x on-disk format. Projects opt in by importing `swirengine.storage15`.

The Python package remains version 1.4.0 until the full 1.5 roadmap reaches 10/10 and the release gate is complete.

## Validation

The dedicated gate covers Python 3.10, 3.13 and 3.14 and verifies:

- envelope integrity and revisions;
- atomic primary/backup behavior;
- corruption fallback and explicit repair;
- safe refusal when both copies are unreadable;
- portable-data validation;
- migrations, defaults and future-version rejection;
- profile isolation and legacy import;
- bounded autosave rotation and ordering;
- slot diagnostics;
- a 250-write autosave workload;
- the runnable Save & Profile 2.0 demo.

Run locally:

```bash
pytest tests/test_save_profile_2_1_5.py
ruff check src/swirengine/storage15.py tests/test_save_profile_2_1_5.py tools/benchmark_save_profile_2_1_5.py examples/demo_save_profile_2_1_5.py
python -m compileall -q src/swirengine/storage15.py tests/test_save_profile_2_1_5.py tools/benchmark_save_profile_2_1_5.py examples/demo_save_profile_2_1_5.py
python tools/benchmark_save_profile_2_1_5.py
python examples/demo_save_profile_2_1_5.py
```
