from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from swirengine.content16 import (
    ContentEntry,
    ContentIntegrityError,
    ContentManifest,
    ContentSafetyError,
    ContentStager,
    ContentStateError,
    VerifiedContentCache,
    apply_patch,
    build_manifest,
    plan_patch,
    verify_tree,
)


def entry(path: str, payload: bytes) -> ContentEntry:
    return ContentEntry(path, hashlib.sha256(payload).hexdigest(), len(payload))


def write(root: Path, relative: str, payload: bytes) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def test_manifest_is_canonical_across_input_order_and_json_round_trip() -> None:
    alpha = entry("data/alpha.bin", b"alpha")
    beta = entry("data/beta.bin", b"beta")
    first = ContentManifest.create("1.6-test", [beta, alpha], metadata={"channel": "test"})
    second = ContentManifest.create("1.6-test", [alpha, beta], metadata={"channel": "test"})

    assert first.entries == (alpha, beta)
    assert first.to_json() == second.to_json()
    assert first.fingerprint == second.fingerprint
    assert ContentManifest.parse_json(first.to_json()) == first
    assert first.total_bytes == 9


def test_manifest_rejects_nonportable_paths_duplicate_paths_and_unknown_json_fields() -> None:
    payload = b"x"
    for invalid in ("../escape", "a/../escape", "/absolute", "C:/drive", "a\\b", "a//b"):
        with pytest.raises(ValueError):
            entry(invalid, payload)

    duplicate = entry("same.bin", payload)
    with pytest.raises(ValueError, match="duplicate"):
        ContentManifest.create("v", [duplicate, duplicate])

    manifest = ContentManifest.create("v", [duplicate])
    data = json.loads(manifest.to_json())
    data["surprise"] = True
    with pytest.raises(ValueError, match="fields"):
        ContentManifest.parse_json(json.dumps(data))


def test_build_manifest_is_deterministic_and_rejects_symlinks(tmp_path: Path) -> None:
    root = tmp_path / "content"
    write(root, "z.bin", b"z")
    write(root, "nested/a.bin", b"a")

    manifest = build_manifest(root, "build-7", metadata={"platform": "test"})
    assert [item.path for item in manifest.entries] == ["nested/a.bin", "z.bin"]
    assert verify_tree(root, manifest).ok

    link = root / "linked.bin"
    try:
        link.symlink_to(root / "z.bin")
    except OSError:
        pytest.skip("symbolic links are unavailable on this host")
    with pytest.raises(ContentSafetyError, match="symbolic-link"):
        build_manifest(root, "build-8")


def test_patch_plan_is_stable_and_counts_only_required_transfer_bytes() -> None:
    keep = entry("keep.bin", b"same")
    old = entry("replace.bin", b"old")
    new = entry("replace.bin", b"new-value")
    removed = entry("removed.bin", b"gone")
    added = entry("new.bin", b"fresh")
    current = ContentManifest.create("1", [removed, old, keep])
    target = ContentManifest.create("2", [new, keep, added])

    plan = plan_patch(current, target)

    assert plan.additions == ("new.bin",)
    assert plan.replacements == ("replace.bin",)
    assert plan.removals == ("removed.bin",)
    assert plan.transfer_bytes == added.size + new.size
    assert plan.changed_files == 3
    assert plan.fingerprint == plan_patch(current, target).fingerprint


def test_verify_tree_reports_missing_hash_size_and_unexpected_files(tmp_path: Path) -> None:
    root = tmp_path / "install"
    good = entry("good.bin", b"good")
    bad_hash = entry("hash.bin", b"expected")
    bad_size = entry("size.bin", b"12345")
    missing = entry("missing.bin", b"missing")
    manifest = ContentManifest.create("v", [good, bad_hash, bad_size, missing])
    write(root, "good.bin", b"good")
    write(root, "hash.bin", b"mismatch")
    write(root, "size.bin", b"x")
    write(root, "extra.bin", b"extra")

    report = verify_tree(root, manifest, reject_unexpected=True)
    codes = {(issue.path, issue.code) for issue in report.issues}

    assert not report.ok
    assert ("hash.bin", "hash_mismatch") in codes
    assert ("size.bin", "size_mismatch") in codes
    assert ("missing.bin", "missing") in codes
    assert ("extra.bin", "unexpected") in codes


def test_verified_cache_rejects_untrusted_bytes_and_detects_tampering(tmp_path: Path) -> None:
    cache = VerifiedContentCache(tmp_path / "cache")
    wanted = entry("asset.bin", b"trusted")

    with pytest.raises(ContentIntegrityError):
        cache.put_bytes(wanted, b"wrong!!")
    path = cache.put_bytes(wanted, b"trusted")
    assert cache.verify(wanted)

    path.write_bytes(b"tampered")
    assert not cache.verify(wanted)
    diagnostics = cache.diagnostics
    assert diagnostics.promotions == 1
    assert diagnostics.rejected_promotions == 1
    assert diagnostics.verified_hits == 1
    assert diagnostics.misses == 1


def test_cache_put_file_reverifies_the_copied_temporary_object(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b"trusted"
    wanted = entry("asset.bin", payload)
    source = write(tmp_path, "source.bin", payload)
    cache = VerifiedContentCache(tmp_path / "cache")

    def corrupt_copy(_source, target, *, length: int) -> None:
        assert length > 0
        target.write(b"corrupt")

    monkeypatch.setattr("swirengine._content16_cache.shutil.copyfileobj", corrupt_copy)

    with pytest.raises(ContentIntegrityError, match="changed during verification"):
        cache.put_file(wanted, source)
    assert not cache.path_for(wanted).exists()
    assert cache.diagnostics.rejected_promotions == 1


def test_resumable_stager_enforces_offsets_and_promotes_only_complete_verified_content(
    tmp_path: Path,
) -> None:
    payload = b"abcdefghij"
    wanted = entry("asset.bin", payload)
    stager = ContentStager(tmp_path / "staging")
    cache = VerifiedContentCache(tmp_path / "cache")

    state = stager.append(wanted, 0, payload[:4])
    assert state.received_bytes == 4
    assert not state.complete
    with pytest.raises(ContentStateError, match="offset mismatch"):
        stager.append(wanted, 0, b"bad")
    state = stager.append(wanted, 4, payload[4:])
    assert state.complete

    cache_path = stager.finalize(wanted, cache)
    assert cache_path.read_bytes() == payload
    assert cache.verify(wanted)
    assert stager.progress(wanted).received_bytes == 0
    assert stager.portable_diagnostics()["resumes"] == 1


def test_resumable_stager_can_continue_a_local_file_from_existing_partial(tmp_path: Path) -> None:
    payload = b"0123456789" * 30
    wanted = entry("large.bin", payload)
    source = write(tmp_path, "source.bin", payload)
    stager = ContentStager(tmp_path / "stage")
    cache = VerifiedContentCache(tmp_path / "cache")

    stager.append(wanted, 0, payload[:73])
    state = stager.stage_local_file(wanted, source, chunk_size=41)
    assert state.complete
    assert stager.finalize(wanted, cache).read_bytes() == payload


def test_stager_discards_complete_partial_when_integrity_fails(tmp_path: Path) -> None:
    wanted = entry("asset.bin", b"correct")
    stager = ContentStager(tmp_path / "stage")
    cache = VerifiedContentCache(tmp_path / "cache")
    stager.append(wanted, 0, b"wrong!!")

    with pytest.raises(ContentIntegrityError, match="failed verification"):
        stager.finalize(wanted, cache)

    assert stager.progress(wanted).received_bytes == 0
    assert stager.integrity_failures == 1
    assert not cache.verify(wanted)


def test_apply_patch_preflights_cache_then_materializes_and_removes(tmp_path: Path) -> None:
    old_keep = entry("keep.bin", b"keep")
    old_replace = entry("sub/change.bin", b"old")
    removed = entry("gone.bin", b"gone")
    new_replace = entry("sub/change.bin", b"new-value")
    added = entry("new.bin", b"brand-new")
    current = ContentManifest.create("1", [old_keep, old_replace, removed])
    target = ContentManifest.create("2", [old_keep, new_replace, added])
    plan = plan_patch(current, target)
    install = tmp_path / "install"
    write(install, "keep.bin", b"keep")
    write(install, "sub/change.bin", b"old")
    write(install, "gone.bin", b"gone")
    cache = VerifiedContentCache(tmp_path / "cache")

    with pytest.raises(ContentIntegrityError, match="unavailable"):
        apply_patch(plan, current, target, cache, install)
    assert (install / "sub/change.bin").read_bytes() == b"old"
    assert (install / "gone.bin").exists()

    cache.put_bytes(new_replace, b"new-value")
    cache.put_bytes(added, b"brand-new")
    report = apply_patch(plan, current, target, cache, install)

    assert report.ok
    assert (install / "keep.bin").read_bytes() == b"keep"
    assert (install / "sub/change.bin").read_bytes() == b"new-value"
    assert (install / "new.bin").read_bytes() == b"brand-new"
    assert not (install / "gone.bin").exists()


def test_apply_patch_refuses_target_fingerprint_mismatch(tmp_path: Path) -> None:
    empty = ContentManifest.create("1", [])
    target = ContentManifest.create("2", [entry("x.bin", b"x")])
    other = ContentManifest.create("3", [entry("y.bin", b"y")])
    plan = plan_patch(empty, target)
    cache = VerifiedContentCache(tmp_path / "cache")

    with pytest.raises(ContentStateError, match="fingerprint"):
        apply_patch(plan, empty, other, cache, tmp_path / "install")


def test_apply_patch_refuses_symlink_parent_escape(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    install = tmp_path / "install"
    install.mkdir()
    link = install / "sub"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links are unavailable on this host")

    payload = b"safe"
    wanted = entry("sub/file.bin", payload)
    current = ContentManifest.create("1", [])
    target = ContentManifest.create("2", [wanted])
    plan = plan_patch(current, target)
    cache = VerifiedContentCache(tmp_path / "cache")
    cache.put_bytes(wanted, payload)

    with pytest.raises(ContentSafetyError, match="symbolic-link"):
        apply_patch(plan, current, target, cache, install)
    assert not (outside / "file.bin").exists()


def test_apply_patch_refuses_wrong_base_manifest_or_modified_install(tmp_path: Path) -> None:
    original = entry("base.bin", b"base")
    wanted = entry("new.bin", b"new")
    current = ContentManifest.create("1", [original])
    target = ContentManifest.create("2", [original, wanted])
    wrong_base = ContentManifest.create("1-other", [original])
    plan = plan_patch(current, target)
    cache = VerifiedContentCache(tmp_path / "cache")
    cache.put_bytes(wanted, b"new")
    install = tmp_path / "install"
    write(install, "base.bin", b"base")

    with pytest.raises(ContentStateError, match="base fingerprint"):
        apply_patch(plan, wrong_base, target, cache, install)
    assert not (install / "new.bin").exists()

    write(install, "base.bin", b"tampered")
    with pytest.raises(ContentStateError, match="base manifest"):
        apply_patch(plan, current, target, cache, install)
    assert not (install / "new.bin").exists()


def test_apply_patch_refuses_unexpected_base_files_before_mutation(tmp_path: Path) -> None:
    wanted = entry("new.bin", b"new")
    current = ContentManifest.create("1", [])
    target = ContentManifest.create("2", [wanted])
    plan = plan_patch(current, target)
    cache = VerifiedContentCache(tmp_path / "cache")
    cache.put_bytes(wanted, b"new")
    install = tmp_path / "install"
    write(install, "untracked.bin", b"unknown")

    with pytest.raises(ContentStateError, match="base manifest"):
        apply_patch(plan, current, target, cache, install)
    assert not (install / "new.bin").exists()
    assert (install / "untracked.bin").read_bytes() == b"unknown"


def test_manifest_payload_has_no_execution_or_remote_fetch_contract() -> None:
    manifest = ContentManifest.create(
        "v",
        [entry("scripts/not-executed.bin", b"print('never run')")],
        metadata={"origin": "local-test"},
    )

    portable = manifest.portable()
    assert "command" not in portable
    assert "url" not in portable
    assert set(portable["entries"][0]) == {"path", "sha256", "size"}


def test_verified_cache_refuses_internal_symlink_parent_escape(tmp_path: Path) -> None:
    outside = tmp_path / "outside-cache"
    outside.mkdir()
    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    objects = cache_root / "objects"
    try:
        objects.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links are unavailable on this host")

    wanted = entry("asset.bin", b"trusted")
    cache = VerifiedContentCache(cache_root)

    with pytest.raises(ContentSafetyError, match="symbolic-link"):
        cache.put_bytes(wanted, b"trusted")
    assert list(outside.iterdir()) == []


def test_stager_refuses_internal_symlink_parent_escape(tmp_path: Path) -> None:
    outside = tmp_path / "outside-stage"
    outside.mkdir()
    stage_root = tmp_path / "stage"
    stage_root.mkdir()
    partial = stage_root / "partial"
    try:
        partial.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links are unavailable on this host")

    wanted = entry("asset.bin", b"trusted")
    stager = ContentStager(stage_root)

    with pytest.raises(ContentSafetyError, match="symbolic-link"):
        stager.append(wanted, 0, b"trusted")
    assert list(outside.iterdir()) == []
