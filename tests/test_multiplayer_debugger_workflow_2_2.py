from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "editor-multiplayer-debugger-2-2.yml"
DOCUMENTATION = ROOT / "docs" / "MULTIPLAYER_DEBUGGER_2_2.md"
CHANGELOG = ROOT / "CHANGELOG.d" / "2.2.0-multiplayer-debugger-sdk.md"


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="ascii")


def test_m9_workflow_is_read_only_validation_for_feature_pr_and_main() -> None:
    workflow = _workflow()
    trigger = workflow.split("permissions:", 1)[0]

    assert 'branches: [main, "feature/2.2-*"]' in trigger
    assert "pull_request:" in trigger
    assert "permissions:\n  contents: read" in workflow
    assert "contents: write" not in workflow
    assert "id-token: write" not in workflow
    assert "gh-action-pypi-publish" not in workflow
    assert "environment: pypi" not in workflow


def test_m9_workflow_keeps_supported_matrix_and_compatibility_gates() -> None:
    workflow = _workflow()

    for version in ("3.10", "3.13", "3.14"):
        assert f'"{version}"' in workflow
    for test_path in (
        "tests/test_network_latency_2_2.py",
        "tests/test_multiplayer_debugger_2_2.py",
        "tests/test_editor_multiplayer_debugger_2_2.py",
        "tests/test_editor_multiplayer_integration_2_2.py",
        "tests/test_editor_extension_sdk_2_2.py",
        "tests/test_editor_extension_tk_2_2.py",
        "tests/test_multiplayer_debugger_shipping_2_2.py",
        "tests/test_multiplayer_2_0.py",
        "tests/test_multiplayer_2_1_4.py",
        "tests/test_multiplayer_replication_1_6.py",
        "tests/test_network_profiler_1_6.py",
        "tests/test_transport_qos_1_6.py",
        "tests/test_ui_designer_authoring_2_2.py",
        "tests/test_ui_designer_runtime_2_2.py",
        "tests/test_ui_designer_editor_2_2.py",
        "tests/test_ui_designer_shipping_2_2.py",
    ):
        assert test_path in workflow
    assert "python tools/generate_progress_svg.py --check" in workflow
    assert "python -m ruff check" in workflow
    assert "python -m compileall -q" in workflow


def test_m9_workflow_requires_real_and_installed_runtime_evidence() -> None:
    workflow = _workflow()

    assert "real_localhost_tcp_peer_round_trip_records_a_real_rtt" in workflow
    assert "SWIR_MULTIPLAYER_DEBUGGER_INSTALLED_ONLY" in workflow
    assert "relocated_export_runs_debugger_and_real_round_trip_from_installed_engine" in workflow
    assert "SWIR_EDITOR_EXTENSIONS_REQUIRE_TK" in workflow
    assert "xvfb-run -a python -m pytest" in workflow


def test_m9_user_facing_artifacts_are_ascii_and_keep_scope_disclaimers() -> None:
    documentation = DOCUMENTATION.read_bytes().decode("ascii")
    changelog = CHANGELOG.read_bytes().decode("ascii")

    assert "not an operating-system sandbox" in documentation
    assert "does not invent latency" in documentation
    assert "does not mark M9 accepted" in documentation
    assert "not a public 2.2 release" in documentation
    assert "not an operating-system sandbox" in changelog
    assert "does not mark M9 accepted" in changelog
