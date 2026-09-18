from __future__ import annotations

import json
import subprocess
import sys

from tools import verify_performance_evidence_2_0 as evidence

EXPECTED_WORKLOADS = {
    "frame-budget",
    "editor-productivity",
    "multiplayer-replication",
    "render-resource-reuse",
    "world-streaming",
    "runtime-scalability",
}


def test_performance_evidence_contract_is_bounded_and_reproducible():
    contract = evidence._load_contract()
    workloads = contract["workloads"]
    assert {item["id"] for item in workloads} == EXPECTED_WORKLOADS
    assert len(workloads) == len(EXPECTED_WORKLOADS)
    for item in workloads:
        path = evidence.ROOT / item["command"]
        assert path.is_file()
        assert item["expected_marker"]
        if item["id"] in evidence.MAX_ALLOWED_BUDGETS:
            assert item["budget_seconds"] == evidence.MAX_ALLOWED_BUDGETS[item["id"]]
            assert item["budget_constant"] in {"BUDGET_SECONDS", "MAX_SECONDS"}
        else:
            assert item["budget_seconds"] is None
            assert item["budget_constant"] is None


def test_competitive_reference_policy_does_not_invent_cross_engine_timing():
    contract = evidence._load_contract()
    policy = contract["measurement_policy"]
    assert policy["cross_engine_runtime_benchmark"] == "not_performed"
    assert "identical" in policy["cross_engine_runtime_reason"].lower()
    references = contract["external_reference_facts"]
    assert {item["project"] for item in references} == {"Arcade", "Panda3D", "Ursina"}
    assert all(item["checked_date"] == evidence.REFERENCE_CHECK_DATE for item in references)
    assert all(item["runtime_performance_compared"] is False for item in references)
    assert all(item["official_url"].startswith("https://") for item in references)
    assert all(item["distribution_url"].startswith("https://") for item in references)


def test_validate_only_emits_contextual_json_without_running_benchmarks(tmp_path):
    output = tmp_path / "evidence.json"
    result = subprocess.run(
        [
            sys.executable,
            "tools/verify_performance_evidence_2_0.py",
            "--validate-only",
            "--output",
            str(output),
        ],
        cwd=evidence.ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "performance evidence OK" in result.stdout
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["results"] == []
    assert payload["context"]["python_implementation"]
    assert payload["context"]["python_version"]
    assert payload["measurement_policy"]["cross_engine_runtime_benchmark"] == "not_performed"


def test_contract_file_is_normal_json_not_generated_runtime_score():
    raw = evidence.CONTRACT_PATH.read_text(encoding="utf-8")
    contract = json.loads(raw)
    assert "harness_elapsed_seconds" not in raw
    assert "results" not in contract
    assert contract["creator_workflow"]["swirengine"]["shipping_evidence"] == (
        "tools/verify_packaging_shipping_2_0.py"
    )
