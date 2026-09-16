# SwirEngine 1.4 — Renderer 2.0

Renderer 2.0 is the additive 3D rendering path introduced during the SwirEngine 1.4 development line.
It keeps the existing 1.x renderer available while adding a modern, explicitly configurable pipeline for
larger 3D scenes.

> Renderer 2.0 is development functionality until the 1.4 Renderer milestone is merged. The stable
> SwirEngine release remains 1.3.0 while the 1.4 roadmap is in progress.

## Quick start

```python
from swirengine import Color, Game, Vec3


game = Game("Renderer 2.0 demo", mode="3d")

game.configure_renderer2(
    shadow_cascades=4,
    shadow_resolution=2048,
    shadow_distance=120.0,
    ssao=True,
    ssao_samples=16,
    bloom=True,
    bloom_levels=5,
    decals=True,
    hdr=True,
)

game.directional_light(direction=Vec3(-0.6, -1.0, -0.35), intensity=1.8)

game.decal(
    position=Vec3(0.0, 0.05, -3.0),
    size=Vec3(3.0, 0.25, 3.0),
    color=Color(0.1, 0.8, 1.0, 0.55),
)

game.run()
```

`Game.configure_renderer2()` is opt-in. Existing 1.x projects keep the established renderer unless the
new path is explicitly enabled.

## Renderer 2.0 frame architecture

The CPU-side `Renderer2Planner` creates a deterministic frame plan before GPU work is submitted. A
production frame can contain the following passes:

1. depth + view-normal prepass
2. cascaded directional shadow maps
3. opaque 3D scene rendering
4. screen-space decal projection
5. SSAO evaluation
6. depth-aware SSAO blur
7. HDR bloom extraction
8. bloom downsample chain
9. bloom upsample chain
10. HDR/post-process resolve

The planner exposes diagnostics before the GPU executes the frame, including visible opaque objects,
prepass draws, shadow cascade/draw counts, decal candidates and drops, SSAO passes, bloom passes and an
estimated draw-call budget.

## Cascaded directional shadows

Renderer 2.0 supports one to four directional shadow cascades. Cascade splits use a practical blend of
uniform and logarithmic distributions. The default split blend is `0.72`.

Each cascade has:

- its own depth target
- camera-relative focus
- texel-snapped positioning for improved temporal stability
- configurable shadow distance and resolution
- 3×3 PCF sampling in the Renderer 2.0 shadow overlay

`Mesh3D` and `Cube3D` both participate as shadow casters and receivers in the current static geometry
path.

## Depth + normal prepass

The prepass writes sampleable scene depth and view-space normals. Those buffers are reused by screen-space
passes rather than reconstructing geometry information independently for every effect.

Current consumers are:

- SSAO
- screen-space decals
- future Renderer 2.0 visibility and depth-driven effects

## SSAO

The SSAO pass uses a deterministic sample kernel and reconstructs view-space positions from the depth
buffer. The result is filtered by a depth-aware 3×3 blur so strong depth discontinuities do not bleed as
aggressively across object boundaries.

Supported sample counts are `8`, `16`, `32` and `64`.

## Bloom + HDR

Bloom uses an HDR bright-pass followed by a configurable downsample/upsample mip chain. The chain is
created lazily and reused while the render size and bloom-level count remain unchanged.

The default configuration uses five bloom levels. `bloom_threshold` and `bloom_intensity` control how
much HDR energy contributes to the final bloom result.

## Decals

`Game.decal(...)` creates a bounded world-space `Decal3D` volume. Renderer 2.0 projects the volume into
screen space by reconstructing world position from the scene depth buffer.

Decals have deterministic ordering and a bounded per-frame budget through `max_decals`. The planner
reports candidate, submitted and dropped decal counts.

Example:

```python
from swirengine import Color, Vec3


game.decal(
    position=Vec3(2.0, 0.1, -5.0),
    size=Vec3(1.5, 0.2, 1.5),
    color=Color(1.0, 0.2, 0.1, 0.7),
    opacity=0.9,
)
```

## Quality settings

`Renderer2Settings` currently exposes:

| Setting | Default | Purpose |
|---|---:|---|
| `cascaded_shadows` | `True` | Enable the CSM path |
| `shadow_cascades` | `4` | Number of shadow cascades, 1–4 |
| `shadow_resolution` | `2048` | Resolution of each cascade depth map |
| `shadow_distance` | `120.0` | Maximum camera distance covered by CSM |
| `shadow_split_lambda` | `0.72` | Uniform/logarithmic split blend |
| `shadow_overlap` | `0.08` | Cascade overlap fraction |
| `depth_prepass` | `True` | Enable sampleable depth/normal prepass |
| `ssao` | `True` | Enable SSAO |
| `ssao_radius` | `0.7` | SSAO search radius |
| `ssao_power` | `1.35` | SSAO response power |
| `ssao_samples` | `16` | SSAO sample count |
| `bloom` | `True` | Enable HDR bloom |
| `bloom_threshold` | `1.05` | Bright-pass threshold |
| `bloom_intensity` | `0.08` | Bloom contribution |
| `bloom_levels` | `5` | Bloom mip-chain depth |
| `decals` | `True` | Enable decal projection |
| `max_decals` | `256` | Maximum submitted decals per frame |
| `hdr` | `True` | Enable HDR resolve path |

Settings are validated atomically. Invalid changes do not replace the last valid `Game.renderer2_settings`
object.

## Compatibility policy

Renderer 2.0 is additive. The legacy 1.x renderer remains the default unless the creator enables
Renderer 2.0. This keeps existing projects compatible while the 1.4 path matures.

Renderer 2.0 currently targets the same OpenGL 3.3 baseline as SwirEngine's established desktop renderer.
The dedicated Renderer 2.0 CI gate creates a software-backed EGL OpenGL 3.3 context and executes CSM,
depth/normal, SSAO, bloom and decal GPU passes on GitHub Actions.

## Validation gates

The milestone is not considered complete merely because unit tests pass. Its dedicated validation covers:

- focused Renderer 2.0 and legacy shadow/postprocess regressions
- headless EGL OpenGL 3.3 shader compilation and GPU execution
- CSM resource allocation/reuse/release checks
- deterministic frame-planner performance budget
- Ruff validation
- compileall validation
- the repository-wide cross-platform CI matrix
- Desktop Export
- Demo Game 3D and Neon Snake 3D regressions

The 1.4 roadmap must remain at 30% until these gates are green and the Renderer 2.0 milestone is merged.
