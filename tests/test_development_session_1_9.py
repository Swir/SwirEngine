from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from swirengine.cli import main, new_project
from swirengine.development19 import DevelopmentRunner, ProjectRunError, parse_environment_assignments
from swirengine.project19 import ProjectManifest, ProjectManifestError


def _project(root: Path, manifest: str, script: str = "print('ok')\n") -> Path:
    root.mkdir()
    (root / "main.py").write_text(script, encoding="utf-8")
    for name in ("assets", "scenes", "scripts"):
        (root / name).mkdir()
    (root / "swirproject.toml").write_text(manifest, encoding="utf-8")
    return root


def test_legacy_manifest_gets_safe_default_run_configuration(tmp_path: Path) -> None:
    root = _project(tmp_path / "legacy", 'name = "Legacy"\nmode = "2d"\n')

    manifest = ProjectManifest.load(root)

    assert manifest.run.entrypoint == "main.py"
    assert manifest.run.arguments == ()
    assert manifest.run.environment == {}
    assert manifest.run.inherit_environment is True


def test_manifest_parses_explicit_run_configuration(tmp_path: Path) -> None:
    root = _project(
        tmp_path / "configured",
        """
name = "Configured"
mode = "3d"

[run]
entrypoint = "main.py"
arguments = ["--level", "intro"]
inherit_environment = false

[run.environment]
SWIR_DIAGNOSTICS = "1"
GAME_CHANNEL = "dev"
""".strip()
        + "\n",
    )

    run = ProjectManifest.load(root).run

    assert run.arguments == ("--level", "intro")
    assert dict(run.environment) == {"GAME_CHANNEL": "dev", "SWIR_DIAGNOSTICS": "1"}
    assert run.inherit_environment is False


def test_manifest_rejects_invalid_run_environment_name(tmp_path: Path) -> None:
    root = _project(
        tmp_path / "bad-env",
        'name = "Bad"\n[run.environment]\n"NOT VALID" = "x"\n',
    )

    with pytest.raises(ProjectManifestError, match="invalid run.environment"):
        ProjectManifest.load(root)


def test_plan_is_deterministic_across_checkout_locations(tmp_path: Path) -> None:
    text = """
name = "Portable"
mode = "2d"
[run]
arguments = ["--seed", "42"]
[run.environment]
GAME_MODE = "test"
""".strip()
    left = _project(tmp_path / "left", text)
    right = _project(tmp_path / "right", text)

    left_plan = DevelopmentRunner.load(left).plan(extra_arguments=("--map", "one"))
    right_plan = DevelopmentRunner.load(right).plan(extra_arguments=("--map", "one"))

    assert left_plan.configuration_fingerprint == right_plan.configuration_fingerprint
    assert left_plan.arguments == ("--seed", "42", "--map", "one")


def test_plan_refuses_missing_development_entrypoint(tmp_path: Path) -> None:
    root = _project(
        tmp_path / "missing",
        'name = "Missing"\n[run]\nentrypoint = "scripts/missing.py"\n',
    )

    with pytest.raises(ProjectRunError, match="entrypoint does not exist"):
        DevelopmentRunner.load(root).plan()


def test_execute_uses_direct_argv_cwd_and_explicit_environment(tmp_path: Path, monkeypatch) -> None:
    root = _project(
        tmp_path / "execute",
        'name = "Execute"\n[run]\ninherit_environment = false\n[run.environment]\nBASE = "one"\n',
    )
    runner = DevelopmentRunner.load(root)
    plan = runner.plan(
        extra_arguments=("literal;not-a-shell",),
        environment_overrides={"EXTRA": "two"},
    )
    captured = {}

    def fake_runner(command, *, cwd, env, check):
        captured.update(command=command, cwd=cwd, env=env, check=check)
        return SimpleNamespace(returncode=0)

    monkeypatch.setenv("SHOULD_NOT_LEAK", "secret")
    result = runner.execute(plan, runner=fake_runner)

    assert result.returncode == 0
    assert captured["command"][-1] == "literal;not-a-shell"
    assert captured["cwd"] == root.resolve()
    assert captured["check"] is False
    assert captured["env"] == {"BASE": "one", "EXTRA": "two"}


def test_cli_dry_run_does_not_start_game_or_print_environment_values(tmp_path: Path, capsys) -> None:
    root = _project(tmp_path / "dry", 'name = "Dry"\n')

    assert main(["run", str(root), "--dry-run", "--set-env", "TOKEN=top-secret"]) == 0
    output = capsys.readouterr().out
    assert "Run plan OK" in output
    assert "TOKEN" in output
    assert "top-secret" not in output


def test_cli_run_executes_controlled_project_with_forwarded_args_and_env(
    tmp_path: Path, capsys
) -> None:
    root = _project(
        tmp_path / "real",
        'name = "Real"\n[run]\ninherit_environment = true\n',
        script="""
import json
import os
import sys
from pathlib import Path
Path("result.json").write_text(
    json.dumps({"args": sys.argv[1:], "value": os.environ.get("SWIR_RUN_TEST")}),
    encoding="utf-8",
)
""".lstrip(),
    )

    assert main(
        ["run", str(root), "--arg", "hello world", "--set-env", "SWIR_RUN_TEST=works"]
    ) == 0
    capsys.readouterr()
    result = json.loads((root / "result.json").read_text(encoding="utf-8"))
    assert result == {"args": ["hello world"], "value": "works"}


def test_environment_assignment_parser_preserves_equals_in_value() -> None:
    assert parse_environment_assignments(["TOKEN=a=b=c"]) == {"TOKEN": "a=b=c"}


@pytest.mark.parametrize("value", ["MISSING_EQUALS", "1BAD=x", "BAD-NAME=x"])
def test_environment_assignment_parser_rejects_invalid_values(value: str) -> None:
    with pytest.raises((ProjectManifestError, ProjectRunError)):
        parse_environment_assignments([value])


def test_new_2d_and_3d_projects_are_immediately_runnable_on_dry_plan(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    for name, mode in (("Game2D", "2d"), ("Game3D", "3d")):
        root = new_project(name, mode)
        plan = DevelopmentRunner.load(root).plan()
        assert plan.entrypoint == "main.py"
        assert plan.arguments == ()
