# SwirEngine 2.0 Multiplayer Production Contract

SwirEngine 2.0 builds a production-facing multiplayer workflow on the existing additive session,
replication, prediction and headless-server foundations. This document describes the new high-level
contract; it does not claim public internet hosting, matchmaking infrastructure or universal network
transport support.

## Compatibility before mutation

Every authoritative session owns a `MultiplayerCompatibility` value with five deterministic fields:

- project id;
- protocol version;
- build id;
- replication-schema id;
- content fingerprint.

A client must match all five before it may join or consume a resume token. Failed compatibility checks
therefore cannot partially mutate the roster, rotate a reconnect token or register a replication stream.
The canonical SHA-256 compatibility fingerprint is suitable for logs, diagnostics and deployment
manifests; it is not an authentication credential.

## Session lifecycle and reconnect

`ProductionMultiplayerSession` composes the existing bounded `SessionLifecycle` and interest-aware
`ReplicationStreamServer` into one creator-facing contract. Join, ready/start/end, disconnect, leave,
interest views, replication acknowledgements and diagnostics use the already tested lower-level systems.

Reconnect uses the existing single-use resume-token lifecycle. A successful resume rotates the token.
When the server already has authoritative world history, reconnect explicitly requests a full
replication resynchronization instead of trusting a stale client delta baseline.

## Authoritative state vs player-local state

The authoritative server API accepts bounded portable gameplay state such as score, health or match
state. The following categories are deliberately rejected from authoritative player-state records:
settings, display, accessibility, controls/input bindings, profile and save data.

`PlayerLocalState` exists only to make the client-owned boundary explicit in creator code. It is not
accepted by the server session and is not emitted by server status or diagnostics. Existing profile/save
systems remain responsible for persistence on the player side.

## Dedicated server path

`DedicatedMultiplayerServer` adapts a production session to the existing `DedicatedServerRuntime` and
`HeadlessRuntimeBoundary`. The registered authoritative component requests only headless-safe network
and storage capabilities. A creator supplies a deterministic `snapshot_factory(ServerTick)`; during an
active match, each dedicated-server tick must produce a `WorldSnapshot` with the same authoritative tick
number. Tick mismatches fail with a stable `snapshot_tick_mismatch` error rather than silently producing
an inconsistent replication timeline.

Before process startup, creators can call `validate_startup()` and emit `deployment_manifest()` to record
headless capability, fixed-tick configuration and the exact compatibility fingerprint. These metadata
operations do not open sockets, start a public service or execute project scripts.

## Example

```python
from swirengine.multiplayer14 import WorldSnapshot
from swirengine.multiplayer20 import (
    DedicatedMultiplayerServer,
    MultiplayerCompatibility,
    ProductionMultiplayerSession,
)

compatibility = MultiplayerCompatibility(
    project_id="my-game",
    protocol_version="2.0",
    build_id="dev-001",
    replication_schema="players-v1",
    content_fingerprint="content-build-fingerprint",
)

session = ProductionMultiplayerSession("server-01", "host", compatibility)

server = DedicatedMultiplayerServer(
    session,
    lambda tick: WorldSnapshot(tick.tick, tick.simulation_time, ()),
)

print(server.validate_startup())
print(server.deployment_manifest())
```

A real game should derive build/content/schema identifiers from its deterministic project and content
pipeline rather than hard-code placeholder values.

## Verification

The dedicated `Multiplayer Production 2.0` workflow runs Python 3.10, 3.13 and 3.14. It covers
compatibility mismatch safety, reconnect token rotation, full resynchronization, authoritative/local
state separation, bounded state payloads, dedicated-server startup/deployment metadata, tick-integrity
failure handling and the maintained multiplayer integration fixture. Existing session, replication and
server regression suites run beside the new tests.

Milestone 3 remains incomplete until the exact final implementation head and the later roadmap-closeout
head pass the required repository-wide compatibility/runtime matrix. No release, release tag or PyPI
publication is authorized by this source work.
