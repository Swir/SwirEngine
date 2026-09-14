# SwirEngine 1.1 creator hardening

- Added an executable 1.1 release-candidate contract that cross-checks target version, Python support, roadmap math, README claims, benchmark gates, sample-game coverage and Trusted Publishing.
- Hardened both complete 3D sample workflows so they remain validation-only and cannot bypass the 1.1 release freeze through automatic GitHub Release creation.
- Kept real OpenGL smoke tests and cross-platform PyInstaller bundles for Neon Cube Hunt 3D and Neon Snake 3D, including packaged Windows runtime probes.
- Strengthened the final publication workflow to rerun performance gates, boot both real 3D games through software OpenGL and rebuild/probe both packaged Windows demos before PyPI can publish.
- Added release-contract regression tests and dedicated documentation for the final 1.1 gate.

No PyPI package, GitHub Release or release tag is created by this milestone while the roadmap is below 10/10.
