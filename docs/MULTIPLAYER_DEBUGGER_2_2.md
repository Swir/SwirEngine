# Multiplayer Debugger and Editor Extension SDK - SwirEngine 2.2 M9

This document defines the Milestone 9 source-development contract. It does not mark M9 accepted
and does not publish SwirEngine 2.2. The verified roadmap remains 8/10 until the exact M9
implementation head and the later merged `main` head complete every required gate.

## Real round-trip measurement

`NetworkRoundTripProbe22` measures elapsed round-trip time from an actual ping/pong exchange. It
uses a monotonic clock at the sender and keeps start times private. Wire packets carry only a
bounded protocol version, sequence and random nonce. Public samples contain only measured
`round_trip_ms`; diagnostics expose bounded aggregate counts and statistics without correlation
values, peer identifiers or clock timestamps.

Pending probes, retained samples and timeouts have hard limits. Invalid, replayed, mismatched and
late packets fail closed. The injectable clock and nonce providers exist for deterministic tests,
while the qualification workflow also performs a real loopback TCP exchange.

Transport impairment settings, QoS scheduling values and configured delays are not measured RTT.
The debugger reports RTT only when a valid probe has completed. It does not invent latency from a
configuration value and makes no physical-network performance claim from loopback evidence.

## Privacy-safe bounded debugger

`MultiplayerDebugger22` attaches only to `ProductionMultiplayerSession` and reads the existing
replication, network-profiler and transport QoS state through a privacy facade. It emits stable
opaque aliases such as `peer-000` and `channel-000`, plus a fixed allowlist of numeric session,
replication, traffic, transport and RTT aggregates.

Snapshots and captures do not expose raw client or session identifiers, compatibility metadata,
resume tokens, network addresses, packet payloads, authoritative player state, filesystem paths or
provider exception text. Clients, channels, counters, retained samples and events are bounded. The
canonical ASCII JSON capture is also capped at 2 MiB, trimmed deterministically when necessary and
fingerprinted with SHA-256.

Provider failures become fixed diagnostic codes or unavailable counters. A privacy-safe capture is
diagnostic evidence, not a claim about public-server capacity, internet latency, frame rate or
physical hardware performance.

## Transient editor controller

`EditorMultiplayerDebugger22` provides explicit attach, detach, sample, snapshot, RTT-source and
capture-export operations over the production runtime. It owns no project-authored state, always
reports clean and is not included in the project save/reopen lifecycle. Closing the project session
releases the attached runtime and all debugger references.

Capture export is an explicit action. The default destination is
`.swir/multiplayer-debugger/capture.json`. Paths must remain portable and below the current
project's `.swir` directory. Writes use a same-directory temporary file, flush/fsync and atomic
replacement. Directory targets, traversal, project-root replacement and symlinked components are
rejected without replacing an existing capture.

## Restricted trusted-installed Python SDK

`EditorExtensionRegistry22` is a narrow host API for trusted, explicitly installed Python
extensions. It is not an operating-system sandbox. Extension code still runs in the SwirEditor
process and can use normal Python imports with that process's permissions. Only extensions already
selected by the host are registered; there is no discovery, autoload, arbitrary module loader or
bridge to the general-purpose `PluginManager`.

Each extension supplies an immutable manifest and requests explicit panel and action capabilities.
The host accepts only bounded declarative panels, display rows and no-argument actions. IDs are
validated and casefold collisions are rejected. Snapshots are deterministic and contain no
callbacks. Lifecycle and callback failures are sanitized, retired contexts cannot publish, and
registry shutdown removes panels and callbacks even when an extension unload hook fails.

The extension context never receives the editor app, project session, Tk root, scene, renderer,
multiplayer session or `PluginManager`. The dynamic Tk host renders only the declarative snapshot.
The built-in multiplayer adapter receives the transient debugger controller, publishes privacy-safe
rows, and routes refresh, capture and detach through no-argument actions. Window close and editor
shutdown cancel polling and unload the registry.

## Export and shipping safety

`.swir` is editor-only state. `ProjectExporter` excludes that root case-insensitively even when a
profile broadly includes `.` or tries to include `.swir` directly. Entrypoints, icons, files or
directories that resolve through `.swir` are rejected. Symlink aliases and unsafe source changes
fail before a previous export directory is cleaned, and desktop shipping uses the same validated
inventory.

The relocation gate exports a representative runtime, moves the stage, makes the authoring project
unavailable and runs from an isolated installed SwirEngine package. The staged application creates
a deterministic probe sample and privacy-safe capture, while no `.swir` diagnostics enter the
artifact. This proves packaging isolation and API behavior; it is not a public 2.2 release or a
physical-network benchmark.

## Qualification boundary

The dedicated workflow is validation-only with `contents: read`. It runs M9 tests plus legacy
multiplayer and M8 UI compatibility on CPython 3.10, 3.13 and 3.14, then checks Ruff, compilation
and deterministic roadmap progress. A separate job requires real localhost TCP RTT, relocated
installed-engine execution and the native Tk extension-host lifecycle under Xvfb.

M9 can be accepted only after all required workflows and checks are green for the exact PR head.
The roadmap counter remains 8/10 until that implementation merges normally and every workflow and
check required for the exact merged `main` SHA is also green.
