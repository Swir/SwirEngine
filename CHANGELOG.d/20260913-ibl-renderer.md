### Added

- Completed the PBR cubemap image-based lighting path with real GPU `samplerCube` sampling, roughness-dependent mip LOD for reflections, low-frequency diffuse environment lighting, AO integration, lazy cubemap caching and deterministic GPU cleanup.
- `Game` now uses the IBL-capable post-process renderer while scenes without an `ImageBasedEnvironment3D` retain the existing rendering path and behavior.
- Renderer live-reload discovery now watches all six enabled cubemap faces and invalidates cached GPU cubemaps when any face changes.
