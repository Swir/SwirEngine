# Session, Lobby & Match Lifecycle — SwirEngine 1.6

SwirEngine 1.6 adds an additive creator-owned session state machine in `swirengine.session16`. It does not replace the stable 1.x networking APIs or change root imports.

The lifecycle model is intentionally transport-independent. A game can keep using the existing TCP/packet layer, a custom transport, or a later 1.6 QoS layer while the session object owns deterministic lobby and match rules.

## State model

`SessionLifecycle` has three explicit phases:

- `lobby` — members may join, change ready state, claim/release roles, and transfer host ownership;
- `match` — roster/lobby mutations are frozen, but disconnect/resume remains available;
- `closed` — terminal state after the final host leaves.

Every successful mutation increments the session revision and emits a monotonically sequenced lifecycle event. Failed operations do not advance revision or silently mutate lifecycle state.

```python
from swirengine.session16 import SessionLifecycle

session = SessionLifecycle("room-42", "host")
guest = session.join("guest")
session.claim_role("guest", "pilot")
session.set_ready("host")
session.set_ready("guest")
snapshot = session.start_match("host")
```

The roster is deterministic by immutable join order. Client identifiers are not used as an accidental ordering source.

## Host and role ownership

The host owns the protected `host` role. Creator-defined roles use a single-owner table:

```python
session.claim_role("guest", "pilot")
assert session.role_owner("pilot") == "guest"
session.release_role("guest", "pilot")
```

The `host` role cannot be claimed or released directly. Host ownership changes only through `transfer_host(current_host, target_client_id)`. A host cannot leave a non-empty session until ownership has been transferred explicitly; this avoids hidden or nondeterministic host promotion rules.

## Ready and match gates

Only connected lobby members may change ready state. `start_match()` is host-only and requires the complete retained roster to be connected and ready. A successful match start moves the phase to `match` atomically.

`end_match()` is also host-only. It returns the session to `lobby` and clears readiness for every member so the next match requires a fresh ready check.

Lobby-only mutations such as join, role ownership changes, host transfer, and ready changes fail with the stable `invalid_phase` diagnostic while a match is active.

## Disconnect and resume

Disconnect is different from leave:

- `disconnect(client_id)` retains roster membership and roles, but sets `connected=False` and clears readiness;
- `leave(client_id)` removes the member, owned roles, and active resume token;
- `resume(token)` restores a disconnected member and rotates the token before returning it.

The creator receives a resume token from `join()` and can query the current token with `resume_token_for(client_id)` when it needs to deliver that secret to the client. Tokens are never included in snapshots, events, or diagnostics.

The default token factory uses `secrets.token_urlsafe(24)`. A deterministic custom `token_factory` can be provided for tests. Returned tokens must be non-empty, at least 8 characters, no longer than 512 characters, and unique among active tokens.

Resume-token storage has a hard `max_resume_tokens` bound. When the bound is exceeded, the oldest active token is expired deterministically and `token_evictions` increases. Resume always rotates the accepted token; replaying the old token fails with `invalid_resume_token`.

Applications should transport resume tokens only over a channel appropriate for authentication/session secrets. The lifecycle API provides bounded local session foundations; it does not claim to be an account identity or cryptographic authentication system.

## Creator-facing events

`events()` returns the retained ordered event stream. `events(since_sequence=N)` returns events with a larger sequence number.

Event examples include:

- `session.hosted`, `session.closed`;
- `member.joined`, `member.left`, `member.disconnected`, `member.resumed`;
- `member.ready`, `member.unready`;
- `role.claimed`, `role.released`, `host.transferred`;
- `match.started`, `match.ended`.

Event retention is bounded by `max_events`. If older entries are evicted, `event_evictions` in diagnostics makes that loss visible instead of pretending the retained deque is a complete audit log.

## Failure diagnostics

Lifecycle rule failures raise `SessionOperationError`. Its `code` is stable and creator-readable. Examples include:

- `invalid_phase`;
- `duplicate_member`, `session_full`, `member_not_found`, `member_disconnected`;
- `host_required`, `host_transfer_required`;
- `protected_role`, `role_owned`, `role_not_owned`;
- `members_not_ready`, `members_disconnected`;
- `invalid_resume_token`, `resume_token_unavailable`, `already_connected`, `already_disconnected`.

`diagnostics()` returns bounded operational counters without exposing token values:

```python
{
    "revision": 12,
    "phase": "lobby",
    "members": 3,
    "connected_members": 3,
    "ready_members": 0,
    "active_resume_tokens": 3,
    "token_evictions": 0,
    "events_emitted": 12,
    "retained_events": 12,
    "event_evictions": 0,
    "successful_mutations": 12,
    "failures_total": 0,
    "failure_counts": {},
}
```

## Snapshot packet bridge

`SessionSnapshot` is immutable and contains only public lifecycle state: session ID, revision, phase, host ID, deterministic members, and role ownership. It deliberately excludes resume tokens.

```python
packet = session.snapshot().to_packet()
wire_bytes = packet.to_bytes()
```

Snapshots use the stable 1.x `NetworkPacket` framing model with packet kind `swir.session16.snapshot`. `SessionSnapshot.from_packet()` validates the member list, host binding, deterministic join order, and agreement between member roles and the role-owner table.

This is a state synchronization bridge, not a remote command executor. Games remain responsible for deciding which authenticated peer is allowed to request host actions.

## Bounds and deterministic behavior

`SessionLifecycle` requires positive hard bounds for:

- `max_members`;
- `max_resume_tokens`;
- `max_events`.

Member IDs, session IDs, roles, event metadata, and packet snapshot fields are validated before use. Boolean values are not accepted where integer counters are required. Snapshot/event metadata must remain JSON-portable and finite.

The dedicated workload benchmark creates 96 members, assigns roles, executes repeated ready/start/end cycles, and performs 160 token-rotating disconnect/resume cycles. It asserts invariant preservation and a 5-second upper budget on the Linux CI runner.

## Compatibility and validation

The 1.6 session lifecycle is additive in `swirengine.session16`. It does not modify stable `ClientPredictor`, replication, transport, or root-import behavior.

The dedicated CI gate runs on Python 3.10, 3.13, and 3.14 and verifies:

- focused session lifecycle tests;
- 1.6 prediction/reconciliation regressions;
- 1.6 interest-aware replication regressions;
- the locked 1.4 multiplayer contract;
- Ruff and `py_compile` checks;
- the deterministic benchmark on Python 3.13;
- the creator demo on every matrix version.

SwirEngine 1.6 must not be tagged or published until all ten roadmap milestones and the final release gate are verified.
