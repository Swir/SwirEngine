# Content Delivery & Patch Manifests — SwirEngine 1.6

SwirEngine 1.6 adds an **opt-in, local-first content delivery foundation** in
`swirengine.content16`. It is intentionally separate from the stable 1.x asset APIs: it identifies
content, plans deterministic file changes, verifies a local content-addressed cache, resumes local
staging, and materializes verified bytes. It does **not** download, import, execute, deserialize, or
launch content automatically.

## Safety model

The content layer treats manifests and staged bytes as untrusted until verification succeeds.
Manifest paths are portable relative POSIX paths. Absolute paths, Windows drive syntax,
backslashes, empty path segments, `.` and `..` traversal are rejected. Filesystem operations reject
symbolic-link parents, so a manifest cannot redirect staging or installation outside the configured
root.

A manifest entry contains only `path`, `sha256`, and `size`. Manifest-level data adds a schema
version, a creator-defined content version, and optional string metadata. There is deliberately no
command, URL, script, Python object, pickle, or executable hook in the format.

## Deterministic manifests

```python
from swirengine.content16 import build_manifest

manifest = build_manifest(
    "build/content",
    "2026.09.17-1",
    metadata={"channel": "internal"},
)
print(manifest.fingerprint)
manifest_json = manifest.to_json()
```

`build_manifest()` walks regular local files without following symlinks. Entries and metadata are
canonicalized before JSON serialization, so the same logical content produces the same SHA-256
manifest fingerprint independently of input ordering.

`ContentManifest.parse_json()` is strict: unknown fields, unsupported schema versions, malformed
hashes, duplicate paths, unsafe paths, and invalid metadata fail explicitly.

## Incremental patch planning

```python
from swirengine.content16 import plan_patch

patch = plan_patch(current_manifest, target_manifest)
print(patch.additions)
print(patch.replacements)
print(patch.removals)
print(patch.transfer_bytes)
```

Patch plans are deterministic and payload-free. Unchanged entries transfer nothing. Additions and
replacements reference the target manifest; removals reference paths that no longer exist in the
target. The plan carries both manifest fingerprints so callers can bind orchestration to exact
content identities.

## Verified local cache

`VerifiedContentCache` stores objects by SHA-256 identity. `put_bytes()` and `put_file()` reject a
payload unless both its size and digest match the declared `ContentEntry`. `verify()` re-hashes an
existing object before it can be used by patch materialization. Cache data is never decoded or
executed.

```python
from swirengine.content16 import VerifiedContentCache

cache = VerifiedContentCache(".swir-content-cache")
cache.put_file(entry, "local-build/data/map.bin")
assert cache.verify(entry)
```

## Resumable local staging

`ContentStager` uses exact byte offsets. A resumed write must start at the current partial size;
out-of-order or overflowing chunks are rejected. `stage_local_file()` resumes from an existing
partial file and `finalize()` promotes it only after full SHA-256 verification. A complete partial
with the wrong digest is discarded rather than entering the verified cache.

```python
from swirengine.content16 import ContentStager

stager = ContentStager(".swir-content-stage")
stager.stage_local_file(entry, "local-build/data/map.bin", chunk_size=1024 * 1024)
stager.finalize(entry, cache)
```

This is the resumable foundation for later transport integrations. SwirEngine 1.6 does not add a
remote fetcher here; a future network provider must deliver bytes into the same explicit staging
contract and cannot bypass integrity verification.

## Applying a verified patch

`apply_patch()` first binds the plan to both the supplied current and target manifest fingerprints,
verifies the installed tree exactly matches the declared base (including absence of unexpected
files), preflights every required cache object, and rejects unsafe target paths before the first
content write. Each transferred file is copied to a sibling temporary file, re-verified, flushed,
and atomically replaced. Removals happen only under the declared install root. The function returns
a final `VerificationReport` for the exact target manifest.

```python
from swirengine.content16 import apply_patch

report = apply_patch(patch, current_manifest, target_manifest, cache, "game-content")
if not report.ok:
    raise RuntimeError(report.portable())
```

The cache also re-verifies the temporary copy made by `put_file()` before promotion, so a source
file that changes after its initial inspection cannot enter the verified object store.

The filesystem update is not advertised as a whole-tree transaction: disk-full or external
filesystem failures can still leave a partially updated tree. The returned final verification makes
that state explicit, and creators can retain the previous content directory or use a platform-owned
atomic directory swap if their deployment requires whole-build rollback.

## Verification and diagnostics

`verify_tree()` can verify only declared entries or additionally report unexpected files. Structured
issues distinguish missing files, size mismatches, hash mismatches, unsafe symlinks, non-regular
paths, and unexpected files. Cache and staging counters expose promotions, rejected promotions,
resume activity, written bytes, and integrity failures without exposing payload contents.

## Compatibility

The module is additive. It does not alter root imports, `AssetManager`, `DerivedAssetCache`, asset
streaming, packaging, networking, or the published SwirEngine 1.5.0 API. SwirEngine 1.6 remains a
source-development checkpoint; no 1.6 GitHub Release or PyPI publication is created.
