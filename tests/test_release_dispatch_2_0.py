from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "release-2.0.yml"
TAG_WORKFLOW = ROOT / ".github" / "workflows" / "tag-2-0.yml"


def test_release_workflow_can_be_dispatched_without_changing_release_source():
    release = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    trigger = release.split("jobs:", 1)[0]

    assert 'tags:\n      - "v2.0.0"' in trigger
    assert "workflow_dispatch:" in trigger
    assert "branches:" not in trigger
    assert release.count('ref: "refs/tags/v2.0.0"') >= 6
    assert '["git", "rev-list", "-n", "1", actual]' in release
    assert '["git", "rev-parse", "HEAD"]' in release
    assert "tag_commit != head_commit" in release
    assert "github.ref_name" not in release
    assert "skip-existing: true" not in release


def test_tag_bridge_preserves_existing_tag_and_dispatches_publication_explicitly():
    tagger = TAG_WORKFLOW.read_text(encoding="utf-8")

    assert "actions: write" in tagger
    assert "workflow_run:" in tagger
    assert 'workflows:\n      - "Final Release Gate 2.0"' in tagger
    assert 'branches:\n      - "main"' in tagger
    assert "github.event.workflow_run.conclusion == 'success'" in tagger
    assert 'test "$WORKFLOW_RUN_HEAD_SHA" = "$main_sha"' in tagger
    assert 'checkout_sha="$(git rev-parse HEAD)"' in tagger
    assert "preserving it without moving or replacing history" in tagger
    assert "git rev-list -n 1 refs/tags/v2.0.0" in tagger
    assert 'select(.name == "Final Release Gate 2.0")' in tagger
    assert "https://pypi.org/pypi/swirengine/2.0.0/json" in tagger
    assert 'echo "dispatch=false" >> "$GITHUB_OUTPUT"' in tagger
    assert "Inconsistent public 2.0 publication state" in tagger
    assert "steps.publication_state.outputs.dispatch == 'true'" in tagger
    assert "gh workflow run release-2.0.yml --ref main" in tagger
    assert "git push --force" not in tagger
