# SwirEngine 1.1 release-candidate gate

SwirEngine 1.1 is intentionally developed without intermediate PyPI or GitHub releases. The only publication path is `.github/workflows/release.yml`, and it must refuse to publish until `ROADMAP_1_1.md` is exactly **10/10 = 100.0%**.

## What is verified before publication

The release contract is executable:

```bash
python tools/verify_1_1_release_candidate.py
python tools/verify_1_1_release_candidate.py --require-complete
```

Normal CI runs the first command on every pull request. The publication workflow runs the second command, which additionally requires all ten roadmap deliverables to be checked.

The verifier keeps the following contracts synchronized:

- target package version `1.1.0` and Python support metadata;
- exactly ten equal-weight roadmap deliverables and a dashboard derived from their checkboxes;
- README release-freeze and platform-support claims;
- benchmark regression gates for static 3D batching and async asset preload;
- both complete 3D sample projects and their OpenGL/bundle validation workflows;
- Windows packaged-runtime probes for both sample games;
- Trusted Publishing for PyPI;
- no `gh release` command and no `contents: write` permission in demo validation workflows.

## Complete sample-game validation

`Neon Cube Hunt 3D` and `Neon Snake 3D` are not treated as screenshot-only examples. Their workflows perform three kinds of checks:

1. project unit tests plus Ruff/compileall;
2. real renderer boot under Xvfb + Mesa software OpenGL;
3. one-file PyInstaller builds on Windows, Linux and macOS, including an actual Windows packaged-runtime probe.

The final publication workflow repeats the real OpenGL boot for both games and builds/probes both Windows executables again. A successful PR smoke is therefore not the only evidence used for a final release.

## Performance evidence

The 1.1 gate reruns deterministic performance checks for the two milestones that currently have quantified regression tests:

- static 3D larger-batch frame preparation;
- asynchronous asset-preload wait reduction.

These are workload-specific regression gates. They must not be presented as universal FPS multipliers.

## Release freeze

Demo workflows are validation-only and have read-only repository permissions. They deliberately do not create GitHub Releases. This prevents a demo change merged to `main` from bypassing the engine-wide 1.1 freeze.

Once the roadmap reaches 10/10 and all final CI/runtime/demo checks are green, the normal release workflow may be invoked. PyPI publication uses GitHub OIDC Trusted Publishing, and the GitHub Release is created only after package publication and every required release job succeeds.
