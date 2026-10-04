from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tools.verify_2_2_1_release_candidate import NEW_WORKFLOW_ENTRY

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / ".github/release-gates/2.2-required-workflows.json"
NEW = ROOT / ".github/release-gates/2.2.1-required-workflows.json"


def test_patch_manifest_appends_one_gate_without_mutating_phase_e_manifest() -> None:
    assert hashlib.sha256(OLD.read_bytes()).hexdigest() == (
        "4b765c20736147881e99bc2a9414265815fbda2013bd20fc32d27be6f189e17a"
    )
    old = json.loads(OLD.read_text(encoding="utf-8"))
    new = json.loads(NEW.read_text(encoding="utf-8"))

    assert new["schema_version"] == old["schema_version"] == 1
    assert new["repository"] == old["repository"] == "Swir/SwirEngine"
    assert len(old["required_workflows"]) == 47
    assert len(new["required_workflows"]) == 48
    assert new["required_workflows"][:-1] == old["required_workflows"]
    assert new["required_workflows"][-1] == NEW_WORKFLOW_ENTRY
