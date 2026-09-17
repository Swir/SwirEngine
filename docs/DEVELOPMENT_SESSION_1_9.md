# Unified Development Session — SwirEngine 1.9

Milestone 2 gives a SwirEngine project one manifest-driven way to start the game during development.
It builds on the validated project contract introduced in Milestone 1 and remains additive for
existing projects.

## Run a project

From a project directory:

```bash
swirengine run .
```

The command loads `swirproject.toml`, validates the configured development entrypoint, builds a direct
argument-vector command using the current Python interpreter, starts it with the project root as the
working directory and returns the game's exit code. SwirEngine does not invoke a shell for project
arguments.

Use a dry run to inspect the launch plan without starting the game:

```bash
swirengine run . --dry-run
```

The CLI prints the deterministic run-configuration fingerprint and environment variable names but
never prints configured environment values.

## Manifest configuration

Projects may add an optional `[run]` table:

```toml
[run]
entrypoint = "main.py"
arguments = ["--level", "intro"]
inherit_environment = true

[run.environment]
SWIR_DIAGNOSTICS = "1"
GAME_CHANNEL = "development"
```

Older manifests without `[run]` keep working: the project entrypoint is used, arguments/environment
are empty and host-environment inheritance remains enabled.

The run entrypoint must remain inside the project. Manifest arguments are bounded strings. Environment
keys use portable identifier syntax and both names and values are bounded before a process can start.

## One-session overrides

Append literal game arguments without changing the project file:

```bash
swirengine run . --arg "--level" --arg "warehouse"
```

Values beginning with `-` can be supplied as `--arg=--level` when required by the command-line parser.
Arguments are passed directly to Python as an argv sequence; they are not evaluated by a shell.

Override environment variables for one run:

```bash
swirengine run . --set-env GAME_CHANNEL=playtest
```

Use `--clean-env` to disable host-environment inheritance or `--inherit-env` to force it for one
session. The final override set is created per launch and does not mutate `os.environ` or global engine
state.

## Programmatic API

`DevelopmentRunner.load(project)` creates a validated project runner. `plan()` returns an immutable
`ProjectRunPlan` containing the argv command, project working directory, environment override names and
a deterministic configuration fingerprint. `execute(plan)` runs it. The runner accepts an injectable
process runner for tests and automation.

The configuration fingerprint intentionally excludes the machine-specific absolute Python executable
path. Equivalent project/run configuration therefore hashes identically in different checkout
locations while the actual command still records the interpreter that will execute the project.

## Production boundary

This command is a development workflow, not the shipping/export workflow. `swirengine export` and
`ProjectExporter` remain responsible for staging and native desktop packaging. Android and Web export
status is unchanged.

SwirEngine 1.9 remains source-only. No 1.9 GitHub Release, release tag or PyPI publication is created.
