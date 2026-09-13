## Added

- Completed opt-in directional GPU shadows for 3D games through `Game.configure_shadows(...)`.
- Added a reusable shadow-aware renderer that renders a directional depth map and resolves receivers with 3x3 PCF, configurable depth bias and normal bias before additive IBL.
- Added an asset-free directional-shadow example plus regression coverage for creator-facing configuration and deterministic shadow-light selection.

## Compatibility

- Directional shadows remain disabled by default, preserving existing 0.4 rendering behavior until a 3D game explicitly opts in.
