from __future__ import annotations

from swirengine.platform16 import PlatformIdentity, PlatformServices


def main() -> None:
    services = PlatformServices.local(
        PlatformIdentity("demo-player", "Demo Player"),
        entitlements=("base-game",),
    )

    first = services.cloud_save("profile", b"level=1", expected_revision=0)
    second = services.cloud_save(
        "profile",
        b"level=2",
        expected_revision=first.revision,
    )
    achievement = services.achievement_progress("first-session", 1.0)
    matches = services.stat_add("matches-played", 1)

    print("capabilities:", [item.value for item in services.capabilities()])
    print("identity:", services.identity().portable())
    print("cloud metadata:", second.portable())
    print("achievement:", achievement.portable())
    print("stat:", matches.portable())
    print("base entitlement:", services.entitlement("base-game").granted)
    print("diagnostics fingerprint:", services.fingerprint())


if __name__ == "__main__":
    main()
