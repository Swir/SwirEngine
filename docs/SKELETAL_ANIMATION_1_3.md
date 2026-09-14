# 3D skeletal animation — SwirEngine 1.3

SwirEngine 1.3 adds an opt-in skeletal path for animated glTF/GLB characters without changing the
existing static `load_gltf(...)` or `load_gltf_scene(...)` contracts.

## Creator API

Skeletal features live in the additive `swirengine.skeletal` namespace while 1.3 is under
development:

```python
from swirengine import Game
from swirengine.skeletal import load_gltf_skeletal

asset = load_gltf_skeletal("character.glb")
character = asset.objects[0]
character.play("Walk")

game = Game("Character", mode="3d")
game.add_many(*asset.objects)
game.run()
```

`GltfSkeletalAsset.clip_names` exposes imported clip names. Every `SkinnedMesh3D` owns a
`SkeletalAnimationController`, so games may change speed/looping, start clips and crossfade:

```python
character.play("Run", fade=0.25)
character.controller.speed = 1.15
```

## glTF coverage

The loader understands the core glTF 2.0 skeletal data used by this milestone:

- node hierarchy and bind-pose TRS,
- `skins[].joints`, optional `skeleton` root and inverse-bind matrices,
- `JOINTS_0` and `WEIGHTS_0`, including normalized unsigned-byte/unsigned-short weights,
- indexed and non-indexed triangle primitives,
- existing SwirEngine glTF material/PBR loading,
- animation channels targeting translation, rotation and scale,
- `STEP`, `LINEAR` and `CUBICSPLINE` interpolation,
- quaternion shortest-path SLERP for linear rotation keys,
- multiple named clips and runtime crossfades.

Morph-target `weights` animation channels are deliberately outside this skeletal milestone and are
not turned into skeletal channels.

## GPU skinning path

Skin deformation runs on the GPU. The production renderer performs an OpenGL 3.3 transform-feedback
pre-pass with four joint influences per vertex. Joint matrices are uploaded through a small float
texture palette (maximum **64 joints per skin**), avoiding fragile uniform-array limits on older GL
3.3 drivers. The skinned position/normal/UV stream then feeds the engine's existing forward renderer,
so the final draw keeps the established texture, Phong/PBR and direct-light behavior.

The palette follows the glTF relationship between the mesh node, current joint transform and inverse
bind matrix. CPU work evaluates clip/keyframe state and the joint palette; vertex deformation remains
on the GPU.

Joint normals use the blended joint matrix's upper 3x3 transform. This is the conventional fast path
for character rigs and assumes skeletal animation does not rely on extreme non-uniform joint scaling.

## Compatibility and renderer boundary

This is additive to stable 1.x. Existing `MeshData`, `Mesh3D`, static glTF loaders, static batching and
GPU instancing remain unchanged.

The initial skeletal path participates in the production direct forward pass. Directional shadow-map
overlay and additive cubemap-IBL auxiliary passes still operate on regular `Mesh3D` objects. SwirEngine
does not silently CPU-skin characters or issue a hidden per-bone fallback for those auxiliary passes.

## Verification

`tests/test_skeletal_animation.py` covers bind poses, palette math, weight normalization, SLERP,
STEP/LINEAR/CUBICSPLINE sampling, crossfade behavior, joint-budget validation and a generated glTF
skin/animation import. It also loads the same generated asset through the legacy static `load_gltf`
entry point as a compatibility regression.

`tools/verify_skeletal_opengl.py` boots the real production renderer under software OpenGL/Xvfb,
executes the transform-feedback GPU skinning path for multiple frames and sends the deformed stream
through the existing PBR forward renderer.
