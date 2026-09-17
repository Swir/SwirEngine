# Unified Run & Development Sessions — SwirEngine 1.9

SwirEngine 1.9 Milestone 2 adds a single manifest-driven development command for both 2D and 3D
projects. It is additive to the stable 1.x runtime: existing projects can keep launching `main.py`
directly, while projects that opt into the production workflow can use `swirengine run`.

## Basic workflow

A project created with:

```bash
swirengine new MyGame --mode 3d
```

contains a `[run]` section and can be checked without starting a window:

```bash
swirengine doctor MyGame
swirengine run MyGame --dry-run
```

Start the game with:

```bash
swirengine run MyGame
```

Arguments after `--` are forwarded directly to the game entrypoint without a shell:

```bash
swirengine run MyGame -- --level arena --difficulty hard
```

The same command and manifest contract are used for 2D and 3D projects.

## Manifest contract

The run section is optional. A project without it inherits safe defaults from the project entrypoint:

```toml
[run]
entrypoint = "main.py"
working_directory = "."
arguments = ["--development"]
inherit_environment = true

[run.environment]
SWIR_CHANNEL = "local"
```

- `entrypoint` is a project-relative Python file and defaults to the project `entrypoint`.
- `working_directory` is project-relative; `.` means the project root.
- `arguments` is a bounded string array prepended to command-line forwarded arguments.
- `inherit_environment` controls whether the child starts from a copy of the parent environment.
- `[run.environment]` contains bounded explicit string overrides.

Absolute paths, traversal, Windows drive escapes, UNC paths, invalid environment names, NUL bytes and
unbounded argument/environment collections are rejected before a process is started.

## Environment overrides

Temporary creator overrides are explicit and affect only the child process:

```bash
swirengine run MyGame --env SWIR_LOG_LEVEL=debug
```

Repeat `--env` for multiple values. Duplicate command-line environment keys are rejected so a launch
plan cannot depend on accidental ordering.

Use an intentionally minimal environment with:

```bash
swirengine run MyGame --clean-env
```

`--clean-env` is opt-in because native libraries and platform launchers may rely on normal host
environment variables. SwirEngine never mutates `os.environ` while planning a run.

## Deterministic planning and diagnostics

Every development session is converted into an immutable `DevelopmentRunPlan` before execution. The
plan records:

- the validated project and run entrypoints;
- the project-contained working directory;
- manifest arguments plus explicitly forwarded arguments;
- declared environment overrides and inheritance policy;
- a portable SHA-256 plan fingerprint.

The fingerprint deliberately excludes checkout location and the host Python path, so semantically
equivalent project/run configurations produce the same identity on different machines.

`swirengine run --dry-run` prints the validated command, working directory, environment policy and
fingerprint without starting the game. Run diagnostics are intentionally separate from packaging-only
checks: a missing export icon can block a shipping profile without preventing a valid development
session.

## Process boundary

The runner invokes the current Python interpreter directly through `subprocess.run` with `shell=False`.
The child exit code becomes the CLI exit code. Startup failures are converted into actionable
`RunSessionError` messages, and keyboard interruption returns the conventional CLI interruption code.

The runner does not daemonize processes, write hidden global configuration or install dependencies.
Those responsibilities stay explicit in the project/environment setup.

## Validation

The dedicated 1.9 run-session gate covers Python 3.10, 3.13 and 3.14, focused manifest/CLI tests,
legacy project/export regressions, Ruff, compile validation and a deterministic 5,000-plan workload.
Repository-wide compatibility and source-checkpoint gates remain authoritative before the roadmap
milestone may be marked complete.

SwirEngine 1.9 is source-only development toward 2.0.

`Release/PyPI: frozen until SwirEngine 2.0`.
