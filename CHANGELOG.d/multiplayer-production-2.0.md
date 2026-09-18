## SwirEngine 2.0 multiplayer production contract

- Added deterministic client/server compatibility fingerprints and pre-mutation join/resume validation.
- Added a production session facade over bounded session lifecycle and interest-aware replication, including full reconnect resynchronization.
- Added explicit separation between authoritative gameplay state and player-local settings/save/profile data, with bounded authoritative payloads.
- Added a validated headless dedicated-server adapter over the existing fixed-tick runtime and extended the maintained multiplayer fixture plus Python 3.10/3.13/3.14 CI coverage.

This remains source development toward SwirEngine 2.0. The public package stays at 1.5.0 and no intermediate release/tag/PyPI publication is created.
