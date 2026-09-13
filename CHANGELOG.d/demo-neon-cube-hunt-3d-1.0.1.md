# Neon Cube Hunt 3D v1.0.1

- explicitly bundle GLFW and glcontext runtime files in standalone demo builds
- validate the final Windows PyInstaller executable by loading its packaged GLFW runtime before publishing it
- add startup failure diagnostics that write `NeonCubeHunt3D-error.log` and show a Windows error dialog
- publish the corrected standalone demo as `demo-neon-cube-hunt-3d-v1.0.1`
