from pathlib import Path

from swirengine.storage import (
    MigrationRegistry,
    ProfileStore,
    SettingSpec,
    SettingsSchema,
)

root = Path(".swirengine-demo-data")
profile = ProfileStore(root, "player-01")
schema = SettingsSchema(
    {
        "volume": SettingSpec(0.8, (int, float), minimum=0.0, maximum=1.0),
        "difficulty": SettingSpec("normal", str, choices=("easy", "normal", "hard")),
        "fullscreen": SettingSpec(False, bool),
    }
)
migrations = MigrationRegistry()

settings = profile.settings(schema, version=1, migrations=migrations, autoload=False)
settings.update({"volume": 0.65, "difficulty": "hard", "fullscreen": True}).save()

slot = profile.save_slot("slot-1", autoload=False)
slot.update({"level": 8, "checkpoint": "reactor", "play_time_seconds": 923.4}).save()

print("profile:", profile.name)
print("settings:", settings.as_dict())
print("slots:", profile.list_slots())
print("diagnostics:", settings.diagnostics)
