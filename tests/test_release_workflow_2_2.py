from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github/workflows/release.yml"
PUBLICATION_GATE_PATH = ROOT / ".github/workflows/publication-gate-2.2.1.yml"
CANDIDATE_PATH = ROOT / ".github/workflows/release-candidate-2.2.1.yml"
CHECKOUT_ACTION = "actions/checkout@11d5960a326750d5838078e36cf38b85af677262"
DOWNLOAD_ACTION = "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093"
PYPI_ACTION = (
    "pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33"
)


def _workflow() -> tuple[str, dict[str, object]]:
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    parsed = yaml.load(text, Loader=yaml.BaseLoader)
    assert isinstance(parsed, dict)
    return text, parsed


def _publication_gate() -> tuple[str, dict[str, object]]:
    text = PUBLICATION_GATE_PATH.read_text(encoding="utf-8")
    parsed = yaml.load(text, Loader=yaml.BaseLoader)
    assert isinstance(parsed, dict)
    return text, parsed


def test_workflow_display_names_are_repository_unique() -> None:
    names: dict[str, Path] = {}
    for path in sorted((ROOT / ".github/workflows").glob("*.y*ml")):
        parsed = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        assert isinstance(parsed, dict)
        name = parsed.get("name")
        assert isinstance(name, str) and name
        assert name not in names, f"duplicate workflow name {name!r}: {names[name]} and {path}"
        names[name] = path


def test_yaml_contract_dependency_is_available_to_every_full_test_run() -> None:
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    release_text, _ = _workflow()
    candidate = CANDIDATE_PATH.read_text(encoding="utf-8")
    gate_text, gate = _publication_gate()

    assert 'dev = ["pytest>=8,<10", "ruff>=0.16,<0.17", "PyYAML>=6,<7"]' in project
    assert '"twine>=7,<8"' in release_text
    assert '"twine>=6,<7"' not in release_text
    assert '"PyYAML>=6,<7"' in candidate
    assert (
        "PyYAML==6.0.3 "
        "--hash=sha256:0f29edc409a6392443abf94b9cf89ce99889a1dd5376d94316ae5145dfedd5d6"
        in gate_text
    )
    for option in (
        "--disable-pip-version-check",
        "--no-deps",
        "--only-binary=:all:",
        "--require-hashes",
    ):
        assert option in gate_text
    assert '".[dev]"' not in gate_text
    assert "pip install --upgrade pip" not in gate_text

    steps = gate["jobs"]["publication-chain"]["steps"]
    setup_index = next(
        i
        for i, step in enumerate(steps)
        if step.get("uses", "").startswith("actions/setup-python@")
    )
    install_index = next(
        i
        for i, step in enumerate(steps)
        if step.get("name") == "Install hashed YAML contract dependency"
    )
    verify_index = next(
        i
        for i, step in enumerate(steps)
        if "verify_2_2_1_release_candidate.py" in step.get("run", "")
    )
    assert setup_index < install_index < verify_index
    chain_step = next(step for step in steps if step.get("id") == "chain")
    assert '--github-output "$GITHUB_OUTPUT"' in chain_step["run"]
    candidate_step = steps[verify_index]
    assert candidate_step["env"] == {
        "CANDIDATE_SOURCE_SHA": "${{ steps.chain.outputs.candidate_source_sha }}"
    }
    candidate_run = candidate_step["run"]
    assert 'git worktree add --detach "$candidate_root" "$CANDIDATE_SOURCE_SHA"' in candidate_run
    assert 'git -C "$candidate_root" rev-parse HEAD' in candidate_run
    assert 'python "$candidate_root/tools/verify_2_2_1_release_candidate.py"' in candidate_run
    assert "python tools/verify_2_2_1_release_candidate.py" not in gate_text


def test_release_identity_waits_for_the_publication_gate_workflow() -> None:
    _, workflow = _workflow()
    triggers = workflow["on"]

    assert isinstance(triggers, dict)
    assert set(triggers) == {"workflow_run"}
    assert triggers["workflow_run"] == {
        "workflows": ["SwirEngine 2.2.1 Publication Gate"],
        "types": ["completed"],
    }
    assert workflow["name"] == "Release"


def test_publication_gate_is_read_only_and_marker_push_only() -> None:
    text, workflow = _publication_gate()
    assert workflow["name"] == "SwirEngine 2.2.1 Publication Gate"
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["on"] == {
        "push": {
            "branches": ["release/2.2.1-publication"],
            "paths": [".release/publish-2.2.1/publication.json"],
        }
    }
    assert "id-token: write" not in text
    assert "contents: write" not in text
    assert "tools/verify_publication_chain_2_2_1.py" in text
    assert "tools/verify_2_2_1_release_candidate.py" in text
    for step in workflow["jobs"]["publication-chain"]["steps"]:
        uses = step.get("uses")
        if uses is not None:
            revision = uses.rpartition("@")[2]
            assert len(revision) == 40
            assert set(revision) <= set("0123456789abcdef")


def test_release_requires_exact_trigger_and_two_marker_chain() -> None:
    text, _ = _workflow()

    required = (
        'test "$GITHUB_REPOSITORY" = "$EXPECTED_REPOSITORY"',
        'test "$GITHUB_EVENT_NAME" = "workflow_run"',
        (
            'test "$TRUSTED_WORKFLOW_REF" = '
            '"$EXPECTED_REPOSITORY/.github/workflows/release.yml@refs/heads/main"'
        ),
        "'.workflow_run.event'",
        "'.workflow_run.path'",
        "'.workflow_run.conclusion'",
        "'.workflow_run.head_repository.full_name'",
        "'.workflow_run.head_branch'",
        "'.workflow_run.head_sha'",
        'test "$remote_tag" = "$PUBLICATION_SHA"',
        "trusted-verifier/tools/verify_publication_chain_2_2_1.py",
        "trusted-verifier/tools/verify_candidate_merge_2_2.py",
        "--tag-policy absent-or-publication",
        "--tag-policy publication",
    )
    for fragment in required:
        assert fragment in text


def test_release_bootstraps_provenance_from_trusted_workflow_source() -> None:
    _, workflow = _workflow()
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    chain = jobs["publication-chain"]
    assert isinstance(chain, dict)
    steps = chain["steps"]
    assert isinstance(steps, list)

    trusted = steps[0]
    target = steps[1]
    assert trusted["uses"] == CHECKOUT_ACTION
    assert trusted["with"] == {
        "ref": "${{ github.workflow_sha }}",
        "persist-credentials": "false",
        "path": "trusted-verifier",
    }
    assert target["uses"] == CHECKOUT_ACTION
    assert target["with"] == {
        "ref": "${{ github.event.workflow_run.head_sha }}",
        "fetch-depth": "0",
        "persist-credentials": "false",
        "path": "publication-source",
    }

    chain_run = next(step["run"] for step in steps if step.get("id") == "chain")
    assert "python trusted-verifier/tools/verify_publication_chain_2_2_1.py" in chain_run
    assert "--root publication-source" in chain_run
    merge_run = next(step["run"] for step in steps if "candidate pull request" in step.get("name", ""))
    assert "python trusted-verifier/tools/verify_candidate_merge_2_2.py" in merge_run
    assert "--root publication-source" in merge_run
    assert "python publication-source/" not in str(steps)


def test_named_exact_sha_workflow_gate_replaces_counting() -> None:
    text, workflow = _workflow()

    assert "verify_required_workflows_2_2.py" in text
    assert '--sha "$CANDIDATE_SOURCE_SHA"' in text
    assert "--manifest .github/release-gates/2.2.1-required-workflows.json" in text
    assert "--mode pull-request" in text
    assert "head_sha=${CANDIDATE_SOURCE_SHA}&event=pull_request" in text
    assert "gh api --paginate --slurp" in text
    assert "required-run-pages.json" in text
    assert "total_count: .[0].total_count" in text
    assert "workflow_runs: [.[].workflow_runs[]]" in text
    assert "EXPECTED_PR_WORKFLOWS" not in text
    assert "count -ge" not in text
    checkout = workflow["jobs"]["required-workflows"]["steps"][0]
    assert checkout["with"]["ref"] == (
        "${{ needs.publication-chain.outputs.candidate_source_sha }}"
    )


def test_release_builds_both_sdists_and_binds_provenance_v2() -> None:
    text, workflow = _workflow()

    required = (
        'git worktree add --detach "$candidate_root" "$CANDIDATE_SOURCE_SHA"',
        "tools/verify_sdist_identity_2_2.py",
        '--candidate "$RUNNER_TEMP/candidate-dist/swirengine-2.2.1.tar.gz"',
        '--publication "$RUNNER_TEMP/publication-dist/swirengine-2.2.1.tar.gz"',
        "tools/release_evidence_2_2_1.py",
        '--candidate-source-commit "$CANDIDATE_SOURCE_SHA"',
        '--candidate-marker-commit "$CANDIDATE_MARKER_SHA"',
        '--publication-commit "$PUBLICATION_SHA"',
        '--expected-workflow-manifest-sha256 "$WORKFLOW_MANIFEST_SHA256"',
        '--expected-logical-sdist-sha256 "$LOGICAL_SDIST_SHA256"',
    )
    for fragment in required:
        assert fragment in text

    build_steps = workflow["jobs"]["build-release"]["steps"]
    install = next(
        step
        for step in build_steps
        if step.get("name") == "Install release validation dependencies"
    )
    regress = next(
        step
        for step in build_steps
        if step.get("name") == "Run complete exact-source tests and static checks"
    )
    materialize = next(
        step
        for step in build_steps
        if step.get("name")
        == "Materialize exact candidate source outside the publication tree"
    )
    publication_build = next(
        step
        for step in build_steps
        if step.get("name") == "Build publication wheel and sdist"
    )
    cache_route = next(
        step
        for step in build_steps
        if step.get("name") == "Route Python caches outside the publication source tree"
    )
    candidate_build = next(
        step
        for step in build_steps
        if step.get("name") == "Build candidate sdist from immutable C"
    )
    distribution_audit = next(
        step
        for step in build_steps
        if step.get("name") == "Validate exact publication distributions"
    )
    distribution_inventory = next(
        step
        for step in build_steps
        if step.get("name") == "Require exact portable artifact names"
    )
    distribution_upload = next(
        step
        for step in build_steps
        if step.get("uses") == "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02"
    )
    assert "env" not in workflow["jobs"]["build-release"]
    assert cache_route["run"] == (
        'echo "PYTHONPYCACHEPREFIX=$RUNNER_TEMP/release-pycache" >> "$GITHUB_ENV"'
    )
    assert build_steps.index(cache_route) < build_steps.index(publication_build)
    assert materialize["env"] == {
        "CANDIDATE_SOURCE_SHA": "${{ needs.publication-chain.outputs.candidate_source_sha }}"
    }
    assert 'git -C "$candidate_root" rev-parse HEAD' in materialize["run"]
    assert install["working-directory"] == "${{ runner.temp }}/candidate-tree"
    assert regress["working-directory"] == "${{ runner.temp }}/candidate-tree"
    assert regress["env"] == {
        "PYTHONPYCACHEPREFIX": "${{ runner.temp }}/candidate-pycache"
    }
    assert "python -m pytest -q -p no:cacheprovider" in regress["run"]
    assert "python -m ruff check --no-cache" in regress["run"]
    assert "status --porcelain --untracked-files=all" in regress["run"]
    assert "working-directory" not in publication_build
    assert (
        'python -m build --wheel --sdist --outdir "$RUNNER_TEMP/publication-dist"'
        in publication_build["run"]
    )
    assert publication_build["run"].count(
        "status --porcelain --untracked-files=all"
    ) == 2
    assert "--outdir publication-dist" not in text
    assert 'candidate_root="$RUNNER_TEMP/candidate-tree"' in candidate_build["run"]
    assert "status --porcelain --untracked-files=all" in candidate_build["run"]
    assert '--outdir "$RUNNER_TEMP/candidate-dist" "$candidate_root"' in candidate_build["run"]
    assert 'twine check "$RUNNER_TEMP/publication-dist"/*' in distribution_audit["run"]
    assert '--dist-dir "$RUNNER_TEMP/publication-dist"' in distribution_audit["run"]
    assert 'os.environ["RUNNER_TEMP"]' in distribution_inventory["run"]
    assert distribution_upload["with"]["path"] == (
        "${{ runner.temp }}/publication-dist/*"
    )
    assert build_steps.index(candidate_build) < build_steps.index(regress)


def test_release_evidence_retry_recovers_only_complete_attested_public_assets() -> None:
    _, workflow = _workflow()
    job = workflow["jobs"]["release-evidence"]
    assert job["permissions"] == {
        "attestations": "read",
        "contents": "read",
    }

    step = next(
        step
        for step in job["steps"]
        if step.get("name") == "Capture initial PyPI, tag and GitHub Release state"
    )
    assert step["env"] == {
        "GH_TOKEN": "${{ github.token }}",
        "CANDIDATE_SOURCE_SHA": (
            "${{ needs.publication-chain.outputs.candidate_source_sha }}"
        ),
        "CANDIDATE_MARKER_SHA": (
            "${{ needs.publication-chain.outputs.candidate_marker_sha }}"
        ),
        "PUBLICATION_SHA": "${{ needs.publication-chain.outputs.publication_sha }}",
        "WORKFLOW_MANIFEST_SHA256": (
            "${{ needs.publication-chain.outputs.workflow_manifest_sha256 }}"
        ),
        "LOGICAL_SDIST_SHA256": (
            "${{ needs.build-release.outputs.logical_sdist_sha256 }}"
        ),
    }
    run = step["run"]

    snapshot_index = run.index("snapshot initial-state/release.json")
    normal_reconcile_index = run.index("if python tools/reconcile_release_2_2_1.py")
    fallback_branch_index = run.index(
        'else\n  echo "Fresh assets differ from public state; '
        'requiring exact immutable release recovery."'
    )
    download_index = run.index('gh release download "$RELEASE_TAG"')
    attestation_index = run.index('gh release verify "$RELEASE_TAG"')
    evidence_index = run.index("python tools/release_evidence_2_2_1.py verify")
    recovery_snapshot_index = run.index("snapshot recovery-state/release.json")
    complete_reconcile_index = run.rindex("python tools/reconcile_release_2_2_1.py")
    snapshot_stage_index = run.index(
        'cp -- "recovery-state/$state_file" "initial-state/$state_file"'
    )
    overwrite_index = run.index('cp -- "$fallback_dir/$asset" "dist/$asset"')
    fallback_end_index = run.index("\nfi\njq . initial-state/plan.json")
    assert (
        snapshot_index
        < normal_reconcile_index
        < fallback_branch_index
        < download_index
        < attestation_index
        < evidence_index
        < recovery_snapshot_index
        < complete_reconcile_index
        < snapshot_stage_index
        < overwrite_index
        < fallback_end_index
    )

    assert run.count("python tools/reconcile_release_2_2_1.py") == 2
    assert run.count("--require-complete") == 1
    assert run.count("--pypi-json initial-state/pypi.json") == 1
    assert run.count("--tag-json initial-state/tag.json") == 1
    assert run.count("--release-json initial-state/release.json") == 1
    assert run.count("--pypi-json recovery-state/pypi.json") == 1
    assert run.count("--tag-json recovery-state/tag.json") == 1
    assert run.count("--release-json recovery-state/release.json") == 1
    assert 'fallback_dir="$(mktemp -d "$RUNNER_TEMP/' in run
    assert 'test "${#release_assets[@]}" -eq 5' in run
    assets_match = re.search(
        r"release_assets=\(\n(?P<body>.*?)\n\s*\)",
        run,
        flags=re.DOTALL,
    )
    assert assets_match is not None
    assert assets_match.group("body").split() == [
        "swirengine-2.2.1-py3-none-any.whl",
        "swirengine-2.2.1-cp314-cp314-win_amd64.whl",
        "swirengine-2.2.1.tar.gz",
        "SHA256SUMS",
        "release-provenance.json",
    ]
    assert '--pattern "$asset"' in run
    assert 'test ! -L "$fallback_dir/$asset"' in run
    assert 'gh release verify-asset "$RELEASE_TAG" "$fallback_dir/$asset"' in run
    assert 'cmp -- "$fallback_dir/$asset" "dist/$asset"' in run
    assert (
        'test "$(find "$fallback_dir" -mindepth 1 -maxdepth 1 -type f | wc -l)" '
        "-eq 5"
    ) in run
    assert (
        'test "$(find dist -mindepth 1 -maxdepth 1 | wc -l)" -eq 5' in run
    )
    assert (
        'test "$(find dist -mindepth 1 -maxdepth 1 -type f | wc -l)" -eq 5'
        in run
    )
    assert "> recovery-state/plan.json" in run
    assert "recovery_files=(pypi.json tag.json release.json plan.json)" in run
    assert 'test "${#recovery_files[@]}" -eq 4' in run
    assert (
        'test "$(find recovery-state -mindepth 1 -maxdepth 1 -type f | wc -l)" '
        "-eq 4"
    ) in run
    assert 'cmp -- "recovery-state/$state_file" "initial-state/$state_file"' in run
    for option in (
        '--candidate-source-commit "$CANDIDATE_SOURCE_SHA"',
        '--candidate-marker-commit "$CANDIDATE_MARKER_SHA"',
        '--publication-commit "$PUBLICATION_SHA"',
        "--workflow-manifest .github/release-gates/2.2.1-required-workflows.json",
        '--expected-workflow-manifest-sha256 "$WORKFLOW_MANIFEST_SHA256"',
        '--expected-logical-sdist-sha256 "$LOGICAL_SDIST_SHA256"',
    ):
        assert option in run
    for mutation in (
        "gh release create",
        "gh release edit",
        "gh release upload",
        "gh release delete",
        "gh api --method",
        "git push",
        "git tag",
        "twine upload",
    ):
        assert mutation not in run


def test_retries_reconcile_fresh_state_and_never_clobber() -> None:
    text, _ = _workflow()

    assert text.count("tools/reconcile_release_2_2_1.py") >= 7
    assert text.count("--initial-pypi-json") >= 4
    assert text.count("--initial-tag-json") >= 4
    assert text.count("--initial-release-json") >= 4
    assert text.count("--pypi-description PYPI_DESCRIPTION_2_2_1.md") == 2
    assert (
        text.count("--pypi-description release-input/PYPI_DESCRIPTION_2_2_1.md") == 6
    )
    assert "--require-complete" in text
    assert "skip-existing" not in text
    assert "--clobber" not in text
    assert "git push --force" not in text
    assert "git tag -f" not in text
    assert text.count("git/ref/heads/${PUBLICATION_BRANCH}") >= 5


def test_read_only_verification_continues_after_intended_write_job_skips() -> None:
    _, workflow = _workflow()
    jobs = workflow["jobs"]

    assert jobs["prepare-pypi"]["if"] == (
        "always() && "
        "needs.publication-chain.result == 'success' && "
        "needs.release-evidence.result == 'success' && "
        "needs.verify-github-release.result == 'success'"
    )
    assert jobs["post-release-public-pypi"]["if"] == (
        "always() && "
        "needs.publication-chain.result == 'success' && "
        "needs.verify-pypi.result == 'success'"
    )
    assert jobs["final-public-state"]["if"] == (
        "always() && "
        "needs.publication-chain.result == 'success' && "
        "needs.release-evidence.result == 'success' && "
        "needs.post-release-public-pypi.result == 'success'"
    )


def test_trusted_publisher_identity_and_minimal_write_permissions_are_preserved() -> None:
    text, workflow = _workflow()
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)

    pypi = jobs["pypi-publish"]
    assert pypi["environment"] == "pypi"
    assert pypi["permissions"] == {"id-token": "write"}
    assert pypi["needs"] == "prepare-pypi"
    assert pypi["if"] == "needs.prepare-pypi.outputs.upload == 'true'"
    assert len(pypi["steps"]) == 2
    assert [step["uses"] for step in pypi["steps"]] == [DOWNLOAD_ACTION, PYPI_ACTION]
    assert all("run" not in step for step in pypi["steps"])
    assert "actions/checkout" not in str(pypi)

    prepare = jobs["prepare-pypi"]
    verify = jobs["verify-pypi"]
    assert prepare["permissions"] == {"contents": "read"}
    assert verify["permissions"] == {"contents": "read"}
    assert "id-token" not in str(prepare.get("permissions"))
    assert "id-token" not in str(verify.get("permissions"))
    assert jobs["prepare-github-release"]["needs"] == [
        "publication-chain",
        "release-evidence",
        "verify-tag",
    ]
    assert jobs["prepare-pypi"]["needs"] == [
        "publication-chain",
        "release-evidence",
        "verify-github-release",
    ]
    assert jobs["post-release-public-pypi"]["needs"] == [
        "publication-chain",
        "verify-pypi",
    ]
    assert text.count("id-token: write") == 1
    assert "pypa/gh-action-pypi-publish@release/v1" not in text
    assert jobs["ensure-tag"]["permissions"] == {"contents": "write"}
    assert jobs["github-release"]["permissions"] == {"contents": "write"}
    assert workflow["permissions"] == {"contents": "read"}


def test_write_jobs_are_minimal_and_never_execute_candidate_code() -> None:
    text, workflow = _workflow()
    jobs = workflow["jobs"]

    assert text.count("contents: write") == 2
    assert jobs["ensure-tag"]["permissions"] == {"contents": "write"}
    assert jobs["github-release"]["permissions"] == {"contents": "write"}

    ensure_tag = jobs["ensure-tag"]
    assert len(ensure_tag["steps"]) == 1
    assert "run" in ensure_tag["steps"][0]
    assert "python" not in ensure_tag["steps"][0]["run"]
    assert "actions/checkout" not in str(ensure_tag)

    github_release = jobs["github-release"]
    assert len(github_release["steps"]) == 2
    assert github_release["steps"][0]["uses"] == DOWNLOAD_ACTION
    assert "run" in github_release["steps"][1]
    assert "python" not in github_release["steps"][1]["run"]
    assert "actions/checkout" not in str(github_release)
    assert "gh release upload" not in text


def test_github_release_requires_server_immutability_and_attestations() -> None:
    text, workflow = _workflow()
    jobs = workflow["jobs"]

    assert "gh release verify \"$RELEASE_TAG\"" in text
    assert "gh release verify-asset \"$RELEASE_TAG\"" in text
    assert "--notes-file github-release-input/RELEASE_NOTES_2_2_1.md" in text
    assert text.count("--release-notes release-input/RELEASE_NOTES_2_2_1.md") == 6
    assert jobs["verify-github-release"]["permissions"] == {
        "attestations": "read",
        "contents": "read",
    }

    evidence_upload = next(
        step
        for step in jobs["release-evidence"]["steps"]
        if step.get("with", {}).get("name") == "swirengine-2.2.1-publication-assets"
    )
    assert set(evidence_upload["with"]["path"].splitlines()) == {
        "dist/*",
        "initial-state/*.json",
        "RELEASE_NOTES_2_2_1.md",
        "PYPI_DESCRIPTION_2_2_1.md",
    }

    create_run = jobs["github-release"]["steps"][1]["run"]
    for name in (
        "swirengine-2.2.1-py3-none-any.whl",
        "swirengine-2.2.1-cp314-cp314-win_amd64.whl",
        "swirengine-2.2.1.tar.gz",
        "SHA256SUMS",
        "release-provenance.json",
    ):
        assert create_run.count(f"github-release-input/{name}") == 1
    assert "github-release-input/*" not in create_run
    assert "--draft" not in create_run
    assert '--title "SwirEngine 2.2.1"' in create_run
    assert "--notes-file github-release-input/RELEASE_NOTES_2_2_1.md" in create_run


def test_release_workflow_pins_every_reusable_action_to_a_full_commit() -> None:
    _, workflow = _workflow()

    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            uses = step.get("uses")
            if uses is None:
                continue
            owner_action, separator, revision = uses.rpartition("@")
            assert separator == "@", owner_action
            assert len(revision) == 40, uses
            assert set(revision) <= set("0123456789abcdef"), uses


def test_release_assets_are_never_built_from_public_registry_state() -> None:
    text, _ = _workflow()

    assert 'ref: ${{ needs.publication-chain.outputs.publication_sha }}' in text
    assert "swirengine==2.2.1" in text
    assert "--index-url https://pypi.org/simple" in text
    assert "--expected-version 2.2.1" in text
    assert "refs/tags/v2.1.0" not in text
