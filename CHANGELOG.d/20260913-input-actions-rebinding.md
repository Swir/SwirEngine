## SwirEngine 1.1 development — input actions and rebinding

- Added creator-facing semantic `InputActions` and immutable `InputBinding` APIs.
- Actions can combine keyboard, mouse, standardized gamepad buttons and directional analog axes.
- Added held/pressed/released queries plus analog action values.
- Added runtime rebinding, duplicate-safe multi-bindings and action removal.
- Added versioned JSON control profiles with save/load support and validation.
- Added regression coverage for mixed-device actions, axis direction/value, rebinding and profile round trips.
- Added `docs/INPUT_ACTIONS.md` with creator examples and controls-menu integration guidance.

Release/PyPI remains frozen until `ROADMAP_1_1.md` reaches 10/10 = 100%.
