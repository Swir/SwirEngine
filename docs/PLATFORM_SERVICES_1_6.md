# Platform Services Abstraction — SwirEngine 1.6

`swirengine.platform16` is an additive, opt-in platform-services layer for creators who need identity, cloud-save, achievement, stat, and entitlement contracts without binding a game to one storefront or online SDK.

The stable 1.x root API is unchanged. Projects can ignore this module entirely, provide one provider for several capabilities, or mix independent providers capability by capability.

## Capability discovery

```python
from swirengine.platform16 import PlatformCapability, PlatformIdentity, PlatformServices

services = PlatformServices.local(
    PlatformIdentity("dev-player", "Developer"),
    entitlements=("base-game",),
)

assert services.supports(PlatformCapability.IDENTITY)
print([capability.value for capability in services.capabilities()])
print(services.provider_name("cloud_save"))
```

A provider is accepted only when it implements the complete method contract for the capability being registered. Missing capability providers fail explicitly with `capability_unavailable`; unsupported operations fail with `unsupported_operation`.

## Offline reference provider

`LocalPlatformProvider` is dependency-free and intentionally local. It is suitable for automated tests, headless validation, prototypes, and creator development. It does **not** pretend to be a durable remote cloud service and does not replace SwirEngine's stable save/profile storage.

```python
from swirengine.platform16 import PlatformIdentity, PlatformServices

services = PlatformServices.local(
    PlatformIdentity("player-1", "Player One"),
    entitlements=("base-game",),
)

first = services.cloud_save("profile", b"revision-one", expected_revision=0)
second = services.cloud_save(
    "profile",
    b"revision-two",
    expected_revision=first.revision,
)

assert second.revision == 2
assert services.achievement_progress("first-win", 1.0).unlocked
assert services.stat_add("matches-played", 1).value == 1.0
assert services.entitlement("base-game").granted
```

Cloud-save payloads are copied on write, bounded by configurable slot/byte limits, and accompanied by SHA-256 metadata. `expected_revision=0` means the creator expects the slot not to exist. Updating or deleting an existing slot can require its current revision, giving providers a deterministic compare-and-swap contract instead of silently overwriting stale data. Per-slot revisions remain monotonic even after a local deletion.

Slot identifiers are portable single path segments; path traversal or nested-path syntax is rejected.

## Achievement, stat, and entitlement contracts

Achievement progress is finite, normalized to `0.0..1.0`, monotonic, and becomes unlocked at `1.0`. Stats accept finite numeric values and expose deterministic ordering. Entitlements are read through the creator-facing facade; the local provider exposes explicit grant/revoke helpers only so tests and local development can configure simulated ownership.

A real storefront integration should implement only the protocols it can truthfully support. The abstraction does not require Steam, Epic, console services, a network connection, or any particular identity vendor.

## Failure isolation

Unexpected provider failures are wrapped as `PlatformServiceError(code="provider_failure")`. The original external exception message is not exposed through the creator-facing error, and a failing identity provider does not disable a separate stats or cloud-save provider.

For optional features, `try_call(...)` converts platform errors into a result object:

```python
result = services.try_call("identity", "identity")
if not result.ok:
    print(result.error_code)
```

This makes capability fallbacks explicit instead of relying on broad exception handling in gameplay code.

## Diagnostics and privacy

`portable_diagnostics()` reports capability availability, provider names, call counts, failure counts, and the last stable error code. It intentionally excludes cloud payload bytes, achievement/stat values, entitlement inventory, identity contents, provider exception text, tokens, and credentials.

`fingerprint()` hashes only that portable diagnostics representation, giving tests and headless runtimes a deterministic comparison surface without serializing player data.

## Integration guidance

- Keep provider SDK initialization outside deterministic gameplay state.
- Discover capabilities before exposing platform-dependent UI.
- Use stable `PlatformServiceError.code` values for creator logic; treat message text as diagnostic only.
- Do not load executable code or unverified remote content through a platform provider.
- Do not assume entitlement availability means identity or cloud-save availability; capabilities are independent.
- Keep secrets and provider tokens inside the integration boundary, never in `portable_diagnostics()`.

SwirEngine 1.6 remains source-only development under the current project release policy. This module does not change the published SwirEngine 1.5.0 compatibility baseline.
