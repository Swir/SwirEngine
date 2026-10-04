# SwirEngine 2.2.1 Release Notes

SwirEngine 2.2.1 is a metadata-only maintenance release for the completed SwirEngine 2.2
Production Tools & Visual Creation line. Public availability is authoritative only when the exact
`v2.2.1` tag, GitHub Release and PyPI project metadata exist. Until that guarded publication
completes, SwirEngine 2.2.0 remains the latest public stable release.

## What changes

- The PyPI project page receives a complete product description instead of the short 2.2.0 summary.
- Installation, 2D and 3D quick starts, project/editor commands, runtime capabilities, multiplayer
  boundaries, SwirEditor tools, examples, support limits and documentation links are explained in
  one package-index document.
- The candidate version and long-description inputs are bound to the exact source used to build the
  future 2.2.1 distributions.

## What does not change

- There are no public API or runtime behavior changes from SwirEngine 2.2.0.
- There are no functional runtime changes from SwirEngine 2.2.0.
- There are no additions, removals or intentional compatibility changes to the public Python API.
- The completed 10/10 SwirEngine 2.2 roadmap scope is unchanged.
- Existing 2.2.0 projects do not require a data migration for this maintenance release.
- Platform, architecture, optional-dependency, host-native packaging and multiplayer-service
  boundaries remain as documented for the 2.2 line.

The complete package-index copy is maintained in `PYPI_DESCRIPTION_2_2_1.md` and is bound as the
project long-description input for the exact release artifacts.

## Compatibility

SwirEngine 2.2.1 retains package metadata for CPython `>=3.10,<3.15`. The maintained release claim
remains limited to the explicitly qualified 64-bit Windows, Linux and macOS hosted-runner matrix;
it does not imply support for 32-bit Python, PyPy, free-threaded CPython, every CPU architecture or
every optional dependency.

## Publication boundary

Changing source version metadata does not publish a package. The existing public command remains:

```bash
python -m pip install -U "swirengine==2.2.0"
```

Only after the guarded 2.2.1 release process succeeds may public documentation switch its stable
installation command to `swirengine==2.2.1` and identify 2.2.1 as published.
