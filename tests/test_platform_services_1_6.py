from __future__ import annotations

import math

import pytest

from swirengine.platform16 import (
    AchievementRecord,
    LocalPlatformProvider,
    PlatformCapability,
    PlatformIdentity,
    PlatformServiceError,
    PlatformServices,
)


def test_local_facade_exposes_all_capabilities_in_stable_order() -> None:
    services = PlatformServices.local(
        PlatformIdentity("player-1", "Player One"),
        entitlements=("base-game",),
    )

    assert services.capabilities() == tuple(PlatformCapability)
    assert all(services.supports(capability) for capability in PlatformCapability)
    assert services.identity() == PlatformIdentity("player-1", "Player One")
    assert services.entitlement("base-game").granted
    assert not services.entitlement("dlc-missing").granted


def test_provider_registration_requires_the_complete_capability_contract() -> None:
    class Incomplete:
        provider_name = "incomplete"

        def cloud_load(self, slot: str):
            return None

    services = PlatformServices()
    with pytest.raises(TypeError, match="missing methods"):
        services.register(PlatformCapability.CLOUD_SAVE, Incomplete())

    assert not services.supports(PlatformCapability.CLOUD_SAVE)


def test_cloud_save_uses_copy_on_write_revision_checks_and_deterministic_slots() -> None:
    services = PlatformServices.local(max_cloud_slots=3)
    mutable = bytearray(b"first")
    first = services.cloud_save("slot-b", mutable, expected_revision=0)
    mutable[:] = b"xxxxx"

    assert first.payload == b"first"
    assert first.revision == 1
    assert len(first.sha256) == 64
    assert services.cloud_load("slot-b") == first

    second = services.cloud_save("slot-b", b"second", expected_revision=1)
    services.cloud_save("slot-a", b"a", expected_revision=0)
    assert second.revision == 2
    assert services.cloud_slots() == ("slot-a", "slot-b")

    with pytest.raises(PlatformServiceError) as conflict:
        services.cloud_save("slot-b", b"stale", expected_revision=1)
    assert conflict.value.code == "cloud_revision_conflict"
    assert services.cloud_load("slot-b") == second


def test_cloud_save_limits_delete_and_revision_monotonicity() -> None:
    services = PlatformServices.local(max_cloud_slots=1, max_cloud_save_bytes=4)

    with pytest.raises(PlatformServiceError) as too_large:
        services.cloud_save("slot", b"12345", expected_revision=0)
    assert too_large.value.code == "cloud_save_too_large"

    first = services.cloud_save("slot", b"1234", expected_revision=0)
    with pytest.raises(PlatformServiceError) as full:
        services.cloud_save("other", b"x", expected_revision=0)
    assert full.value.code == "cloud_slot_limit"

    assert services.cloud_delete("slot", expected_revision=first.revision)
    assert services.cloud_load("slot") is None
    second = services.cloud_save("slot", b"x", expected_revision=0)
    assert second.revision == 2


def test_cloud_identifiers_are_portable_single_segments() -> None:
    services = PlatformServices.local()

    for invalid in ("", ".", "..", "../escape", "folder/slot", r"folder\slot"):
        with pytest.raises(PlatformServiceError) as invalid_slot:
            services.cloud_save(invalid, b"x", expected_revision=0)
        assert invalid_slot.value.code == "provider_failure"


def test_achievement_progress_is_monotonic_and_unlock_is_idempotent() -> None:
    services = PlatformServices.local()

    assert services.achievement("first-win") == AchievementRecord("first-win", 0.0, False)
    halfway = services.achievement_progress("first-win", 0.5)
    unlocked = services.achievement_progress("first-win", 1.0)
    again = services.achievement_progress("first-win", 1.0)

    assert halfway.progress == 0.5
    assert unlocked.unlocked
    assert again == unlocked
    assert services.achievements() == (unlocked,)

    with pytest.raises(PlatformServiceError) as regression:
        services.achievement_progress("first-win", 0.75)
    assert regression.value.code == "achievement_regression"


def test_stats_are_finite_and_deterministically_ordered() -> None:
    services = PlatformServices.local()

    assert services.stat("score").value == 0.0
    assert services.stat_set("score", 10).value == 10.0
    assert services.stat_add("score", 2.5).value == 12.5
    services.stat_set("alpha", -3)
    assert [item.stat_id for item in services.stats()] == ["alpha", "score"]

    for invalid in (math.inf, -math.inf, math.nan):
        with pytest.raises(PlatformServiceError) as invalid_stat:
            services.stat_set("bad", invalid)
        assert invalid_stat.value.code == "provider_failure"


def test_local_entitlement_mutation_is_explicit_and_facade_is_read_only() -> None:
    provider = LocalPlatformProvider(entitlements=("base",))
    services = PlatformServices(
        {
            PlatformCapability.ENTITLEMENTS: provider,
            PlatformCapability.IDENTITY: provider,
        }
    )

    assert services.entitlement("base").granted
    assert not services.entitlement("dlc").granted
    provider.grant_entitlement("dlc")
    assert services.entitlement("dlc").granted
    provider.revoke_entitlement("base")
    assert not services.entitlement("base").granted
    assert [item.entitlement_id for item in services.entitlements()] == ["base", "dlc"]


def test_safe_call_contains_provider_failure_without_disabling_other_capabilities() -> None:
    class BrokenIdentity:
        provider_name = "broken"

        def identity(self):
            raise RuntimeError("upstream offline")

    local = LocalPlatformProvider()
    services = PlatformServices(
        {
            PlatformCapability.IDENTITY: BrokenIdentity(),
            PlatformCapability.STATS: local,
        }
    )

    result = services.try_call(PlatformCapability.IDENTITY, "identity")
    assert not result.ok
    assert result.error_code == "provider_failure"
    assert "RuntimeError" in (result.error_message or "")
    assert "upstream offline" not in (result.error_message or "")

    assert services.stat_add("survived", 1).value == 1.0
    diagnostics = services.portable_diagnostics()["capabilities"]
    assert diagnostics["identity"]["failures"] == 1
    assert diagnostics["identity"]["last_error_code"] == "provider_failure"
    assert diagnostics["stats"]["failures"] == 0


def test_capability_unavailable_and_unknown_operation_are_explicit() -> None:
    services = PlatformServices()

    with pytest.raises(PlatformServiceError) as unavailable:
        services.identity()
    assert unavailable.value.code == "capability_unavailable"

    local = LocalPlatformProvider()
    services.register(PlatformCapability.IDENTITY, local)
    with pytest.raises(PlatformServiceError) as unsupported:
        services.call(PlatformCapability.IDENTITY, "delete_everything")
    assert unsupported.value.code == "unsupported_operation"


def test_unregister_changes_discovery_without_touching_other_services() -> None:
    services = PlatformServices.local()

    assert services.unregister("cloud_save")
    assert not services.supports("cloud_save")
    assert services.supports("stats")
    assert not services.unregister("cloud_save")


def test_diagnostics_and_fingerprint_are_payload_free_and_deterministic() -> None:
    first = PlatformServices.local()
    second = PlatformServices.local()
    first.cloud_save("private", b"secret-data", expected_revision=0)
    second.cloud_save("private", b"different-secret", expected_revision=0)

    first_diag = first.portable_diagnostics()
    second_diag = second.portable_diagnostics()
    assert first_diag == second_diag
    assert "secret-data" not in repr(first_diag)
    assert "different-secret" not in repr(second_diag)
    assert first.fingerprint() == second.fingerprint()


def test_identity_and_record_validation_reject_malformed_values() -> None:
    with pytest.raises(ValueError):
        PlatformIdentity("", "Player")
    with pytest.raises(ValueError):
        AchievementRecord("achievement", 1.5, False)
    with pytest.raises(ValueError):
        AchievementRecord("achievement", 0.5, True)


def test_split_providers_do_not_require_a_storefront_or_network_dependency() -> None:
    identity = LocalPlatformProvider(PlatformIdentity("offline", "Offline"))
    progression = LocalPlatformProvider()

    services = PlatformServices(
        {
            PlatformCapability.IDENTITY: identity,
            PlatformCapability.ACHIEVEMENTS: progression,
            PlatformCapability.STATS: progression,
        }
    )

    assert services.identity().provider == "local"
    assert services.achievement_progress("offline-win", 1.0).unlocked
    assert services.stat_add("matches", 1).value == 1.0
    assert not services.supports(PlatformCapability.CLOUD_SAVE)
    assert not services.supports(PlatformCapability.ENTITLEMENTS)
