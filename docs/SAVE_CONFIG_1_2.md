# Save/config expansion — SwirEngine 1.2

SwirEngine 1.2 keeps the original `SaveStore` contract and plain-object JSON format intact while adding an opt-in production layer for typed settings, schema migrations and profile-oriented save layouts.

## Typed settings

`SettingSpec` describes the allowed Python type, default value, optional choices and numeric range for one setting. `SettingsSchema` validates defaults at construction time and rejects unknown keys by default, making bad settings fail close to the write that introduced them rather than later in gameplay code.

```python
from swirengine.storage import SettingSpec, SettingsSchema, SettingsStore

schema = SettingsSchema(
    {
        "volume": SettingSpec(0.8, (int, float), minimum=0.0, maximum=1.0),
        "difficulty": SettingSpec("normal", str, choices=("easy", "normal", "hard")),
        "fullscreen": SettingSpec(False, bool),
    }
)
settings = SettingsStore("user-data/settings.json", schema, version=1)
settings.set("volume", 0.6).set("fullscreen", True).save()
```

`SettingsStore` writes a small explicit envelope:

```json
{
  "format": "swirengine-settings",
  "values": {
    "difficulty": "normal",
    "fullscreen": true,
    "volume": 0.6
  },
  "version": 1
}
```

Files with a future schema version are rejected instead of silently discarding data.

## Deterministic migrations

Migrations advance exactly one schema version at a time. Every intermediate step must be registered, so a project cannot accidentally skip an old save/config transformation.

```python
from swirengine.storage import MigrationRegistry

migrations = MigrationRegistry()
migrations.register(
    1,
    lambda values: {
        "volume": values.pop("master_volume") / 100.0,
        **values,
    },
)
```

When `SettingsStore(..., version=2, migrations=migrations)` opens a version-1 file, the migration runs before current-schema validation. `StorageDiagnostics.migrations` records how many steps were applied.

## Profile and save-slot layout

`ProfileStore` separates settings from independent save slots:

```text
user-data/
└── profiles/
    └── player-01/
        ├── settings.json
        └── saves/
            ├── autosave.json
            ├── slot-1.json
            └── slot-2.json
```

This avoids one monolithic frequently-mutated file. External backup/cloud-sync systems can synchronize settings and individual slots independently. Profile and slot tokens reject traversal characters and are limited to stable filename-safe identifiers.

```python
from swirengine.storage import ProfileStore

profile = ProfileStore("user-data", "player-01")
profile.save_slot("slot-1", autoload=False).update(
    {"level": 8, "checkpoint": "reactor"}
).save()
print(profile.list_slots())
```

## Atomic-write contract

Both the existing `SaveStore` and new `SettingsStore` write UTF-8 JSON through a unique temporary file in the destination directory, flush it, call `fsync`, and then replace the target with `os.replace`. Temporary files are cleaned on failure. The unique name avoids two independent stores accidentally sharing the old fixed `.tmp` path.

The operation protects against partially written JSON at the application level; it is not a transactional multi-file database. Games that need cross-file transactions should keep related state in one save slot or add an application-specific journal.

## Compatibility

- Existing `SaveStore` constructors, mapping helpers and on-disk plain JSON objects remain valid.
- The new typed/versioned settings envelope is opt-in through `SettingsStore`.
- No automatic migration is performed on an existing plain `SaveStore` file.
- Settings migrations are explicit and deterministic; downgrade migrations are intentionally unsupported.
