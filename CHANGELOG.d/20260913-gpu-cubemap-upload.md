# GPU cubemap upload hardening

- Added `CubemapGPUTexture`, an owned GPU resource wrapper with safe `use`, shape-preserving `replace`, idempotent `release`, and mipmap tracking.
- Added `upload_cubemap()` plus `ImageBasedEnvironment3D.upload()` for deterministic six-face ModernGL `TextureCube` uploads in OpenGL face order.
- Added strict CPU payload validation and failure-safe cleanup when a face upload raises.
- Added regression tests covering face order, alignment, mipmaps, replacement validation, binding and release behavior.

Roadmap progress is intentionally unchanged: true IBL remains incomplete until the PBR renderer samples the cubemap for diffuse/specular environment lighting.
