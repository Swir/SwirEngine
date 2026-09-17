from __future__ import annotations

import json
from pathlib import Path

import pytest

from swirengine.cli import main, new_project
from swirengine.project19 import ProjectManifest, ProjectManifestError
from swirengine.run_sessions19 import RunSessionError, create_run_plan


def _project(root: Path, manifest_text: str, *, entrypoint: str = "main.py") -> Path:
    root.mkdir()
    (root / "assets").mkdir()
    (root / "scenes").mkdir()
    (root / "scripts").mkdir()
    entrypoint_path = root / entrypoint
    entrypoint_path.parent.mkdir(parents=True, exist_ok=True)
    entrypoint_path.write_text("print('run fixture')\n", encoding="utf-8")
    (root / "swirproject.toml").write_text(manifest_text, encoding="utf-8")
    return root


def test_manifest_run_config_is_portable_and_bounded(tmp_path: Path) -> None:
    root = _project(
        tmp_path / "configured",
        """
name = "Configured"
mode = "3d"
entrypoint = "main.py"

[run]
entrypoint = "scripts/dev.py"
working_directory = "scripts"
arguments = ["--level", "arena"]
inherit_environment = false

[run.environment]
SWIR_CHANNEL = "development"
""".strip()
        + "\n",
        entrypoint="scripts/dev.py",
    )

    manifest = ProjectManifest.load(root)

    assert manifest.run.entrypoint == "scripts/dev.py"
    assert manifest.run.working_directory == "scripts"
    assert manifest.run.arguments == ("--level", "arena")
    assert manifest.run.environment == {"SWIR_CHANNEL": "development"}
    assert manifest.run.inherit_environment is False


def test_legacy_manifest_gets_safe_default_run_config(tmp_path: Path) -> None:
    root = _project(tmp_path / "legacy", 'name = "Legacy"\nentrypoint = "main.py"\n')

    manifest = ProjectManifest.load(root)

    assert manifest.run.entrypoint == "main.py"
    assert manifest.run.working_directory == "."
    assert manifest.run.arguments == ()
    assert manifest.run.environment == {}
    assert manifest.run.inherit_environment is True


@pytest.mark.parametrize(
    "manifest, match",
    [
        (
            'name = "Bad"\n[run]\nworking_directory = "../outside"\n',
            "inside the project",
        ),
        (
            'name = "Bad"\n[run.environment]\n"9INVALID" = "value"\n',
            "variable names",
        ),
        (
            'name = "Bad"\n[run]\narguments = [1]\n',
            "only strings",
        ),
    ],
)
def test_run_config_rejects_unsafe_or_ambiguous_values(
    tmp_path: Path,
    manifest: str,
    match: str,
) -> None:
    root = _project(tmp_path / "bad", manifest)

    with pytest.raises(ProjectManifestError, match=match):
        ProjectManifest.load(root)


def test_run_plan_is_portable_and_does_not_mutate_parent_environment(
    tmp_path: Path, monkeypatch
) -> None:
    manifest_text = """
name = "Portable"
entrypoint = "main.py"

[run]
arguments = ["--from-manifest"]

[run.environment]
SWIR_DECLARED = "manifest"
""".strip() + "\n"
    left = _project(tmp_path / "left", manifest_text)
    right = _project(tmp_path / "right", manifest_text)
    monkeypatch.setenv("SWIR_PARENT_ONLY", "parent")

    left_plan = create_run_plan(
        ProjectManifest.load(left),
        forwarded_args=("--from-cli", "value"),
        environment_overrides=("SWIR_DECLARED=override", "SWIR_EXTRA=1"),
    )
    right_plan = create_run_plan(
        ProjectManifest.load(right),
        forwarded_args=("--from-cli", "value"),
        environment_overrides=("SWIR_DECLARED=override", "SWIR_EXTRA=1"),
    )

    assert left_plan.fingerprint == right_plan.fingerprint
    assert left_plan.arguments == ("--from-manifest", "--from-cli", "value")
    child_environment = left_plan.build_environment({"SWIR_PARENT_ONLY": "parent"})
    assert child_environment == {
        "SWIR_PARENT_ONLY": "parent",
        "SWIR_DECLARED": "override",
        "SWIR_EXTRA": "1",
    }
    assert left_plan.environment["SWIR_DECLARED"] == "override"


def test_clean_environment_is_explicit_and_deterministic(tmp_path: Path) -> None:
    root = _project(
        tmp_path / "clean",
        """
name = "Clean"
[run.environment]
ONLY_THIS = "yes"
""".strip()
        + "\n",
    )

    plan = create_run_plan(ProjectManifest.load(root), clean_environment=True)

    assert plan.inherit_environment is False
    assert plan.build_environment({"SHOULD_NOT_LEAK": "1"}) == {"ONLY_THIS": "yes"}


def test_run_plan_rejects_duplicate_or_invalid_environment_overrides(tmp_path: Path) -> None:
    root = _project(tmp_path / "overrides", 'name = "Overrides"\n')
    manifest = ProjectManifest.load(root)

    with pytest.raises(RunSessionError, match="duplicate"):
        create_run_plan(manifest, environment_overrides=("A=1", "A=2"))

    with pytest.raises(ProjectManifestError, match="variable names"):
        create_run_plan(manifest, environment_overrides=("9BAD=value",))


def test_run_diagnostics_ignore_packaging_only_failures(tmp_path: Path) -> None:
    root = _project(
        tmp_path / "diagnostics",
        """
name = "Diagnostics"
entrypoint = "main.py"

[profiles.windows]
target = "windows"
icon = "missing.ico"
""".strip()
        + "\n",
    )

    manifest = ProjectManifest.load(root)

    assert any(item.code == "profile-icon-missing" for item in manifest.diagnostics())
    assert not any(item.severity == "error" for item in manifest.run_diagnostics())


def test_cli_run_dry_run_supports_2d_and_3d_projects(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.chdir(tmp_path)

    for name, mode in (("Game2D", "2d"), ("Game3D", "3d")):
        root = new_project(name, mode)
        assert main(["run", str(root), "--dry-run"]) == 0
        output = capsys.readouterr().out
        assert f"Development session: {name} ({mode})" in output
        assert "Run plan fingerprint:" in output
        assert "Dry run: game process was not started" in output


def test_cli_run_forwards_arguments_and_environment_without_shell(
    tmp_path: Path, capsys
) -> None:
    root = tmp_path / "actual"
    root.mkdir()
    for sub in ("assets", "scenes", "scripts", "runtime"):
        (root / sub).mkdir()
    (root / "scripts" / "dev.py").write_text(
        """
import json
import os
import sys
from pathlib import Path

Path("result.json").write_text(
    json.dumps(
        {
            "args": sys.argv[1:],
            "declared": os.environ.get("DECLARED"),
            "override": os.environ.get("OVERRIDE"),
            "cwd": Path.cwd().name,
        },
        sort_keys=True,
    ),
    encoding="utf-8",
)
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (root / "swirproject.toml").write_text(
        """
name = "Actual"
mode = "2d"
entrypoint = "scripts/dev.py"

[content]
include = ["assets", "scenes", "scripts"]

[run]
entrypoint = "scripts/dev.py"
working_directory = "runtime"
arguments = ["manifest-arg"]

[run.environment]
DECLARED = "yes"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    assert (
        main(
            [
                "run",
                str(root),
                "--env",
                "OVERRIDE=cli",
                "--",
                "--difficulty",
                "hard",
            ]
        )
        == 0
    )

    result = json.loads((root / "runtime" / "result.json").read_text(encoding="utf-8"))
    assert result == {
        "args": ["manifest-arg", "--difficulty", "hard"],
        "cwd": "runtime",
        "declared": "yes",
        "override": "cli",
    }
    assert "Development session: Actual (2d)" in capsys.readouterr().out


def test_cli_run_reports_missing_entrypoint_before_process_start(
    tmp_path: Path, capsys
) -> None:
    root = tmp_path / "missing"
    root.mkdir()
    (root / "swirproject.toml").write_text(
        'name = "Missing"\n[run]\nentrypoint = "missing.py"\n',
        encoding="utf-8",
    )

    assert main(["run", str(root)]) == 2
    assert "run-entrypoint-missing" in capsys.readouterr().err


def test_run_plan_fingerprint_changes_with_forwarded_configuration(tmp_path: Path) -> None:
    root = _project(tmp_path / "fingerprint", 'name = "Fingerprint"\n')
    manifest = ProjectManifest.load(root)

    first = create_run_plan(manifest, forwarded_args=("one",))
    second = create_run_plan(manifest, forwarded_args=("two",))

    assert first.fingerprint != second.fingerprint
