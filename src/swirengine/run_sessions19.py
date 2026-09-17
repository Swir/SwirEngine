from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from .project19 import ProjectDiagnostic, ProjectManifest

_MAX_FORWARDED_ARGS = 128
_MAX_ARGUMENT_LENGTH = 4096


class RunSessionError(RuntimeError):
    """Raised when a development session cannot be planned or started safely."""


@dataclass(slots=True, frozen=True)
class DevelopmentRunPlan:
    """Immutable, inspectable plan for one manifest-driven development session."""

    project_root: Path
    working_directory: Path
    entrypoint: Path
    arguments: tuple[str, ...]
    environment: Mapping[str, str]
    inherit_environment: bool
    manifest_fingerprint: str

    @property
    def command(self) -> tuple[str, ...]:
        return (sys.executable, str(self.entrypoint), *self.arguments)

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(
            {
                "manifest": self.manifest_fingerprint,
                "entrypoint": self.entrypoint.relative_to(self.project_root).as_posix(),
                "working_directory": (
                    "."
                    if self.working_directory == self.project_root
                    else self.working_directory.relative_to(self.project_root).as_posix()
                ),
                "arguments": list(self.arguments),
                "environment": dict(sorted(self.environment.items())),
                "inherit_environment": self.inherit_environment,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def build_environment(self, base: Mapping[str, str] | None = None) -> dict[str, str]:
        """Return a new process environment without mutating global os.environ."""

        if self.inherit_environment:
            source = os.environ if base is None else base
            environment = {str(key): str(value) for key, value in source.items()}
        else:
            environment = {}
        environment.update(self.environment)
        return environment

    def to_dict(self) -> dict[str, object]:
        return {
            "project": self.project_root.name,
            "entrypoint": self.entrypoint.relative_to(self.project_root).as_posix(),
            "working_directory": (
                "."
                if self.working_directory == self.project_root
                else self.working_directory.relative_to(self.project_root).as_posix()
            ),
            "arguments": list(self.arguments),
            "environment": dict(sorted(self.environment.items())),
            "inherit_environment": self.inherit_environment,
            "fingerprint": self.fingerprint,
        }


def create_run_plan(
    manifest: ProjectManifest,
    *,
    forwarded_args: Sequence[str] = (),
    environment_overrides: Iterable[str] = (),
    clean_environment: bool = False,
) -> DevelopmentRunPlan:
    diagnostics = manifest.run_diagnostics()
    errors = [item for item in diagnostics if item.severity == "error"]
    if errors:
        summary = "; ".join(_diagnostic_summary(item) for item in errors)
        raise RunSessionError(f"project is not runnable: {summary}")

    extra_args = _validated_arguments(forwarded_args, label="forwarded argument")
    overrides = _parse_environment_overrides(environment_overrides)
    merged_environment = dict(manifest.run.environment)
    merged_environment.update(overrides)

    root = manifest.root.resolve()
    entrypoint = (root / manifest.run.entrypoint).resolve()
    working_directory = (
        root
        if manifest.run.working_directory == "."
        else (root / manifest.run.working_directory).resolve()
    )

    _require_inside_project(root, entrypoint, label="run entrypoint")
    _require_inside_project(root, working_directory, label="run working directory")

    return DevelopmentRunPlan(
        project_root=root,
        working_directory=working_directory,
        entrypoint=entrypoint,
        arguments=(*manifest.run.arguments, *extra_args),
        environment=MappingProxyType(merged_environment),
        inherit_environment=manifest.run.inherit_environment and not clean_environment,
        manifest_fingerprint=manifest.fingerprint,
    )


def execute_run_plan(plan: DevelopmentRunPlan) -> int:
    """Execute a validated plan without a shell and return the child process exit code."""

    try:
        completed = subprocess.run(
            plan.command,
            cwd=plan.working_directory,
            env=plan.build_environment(),
            check=False,
        )
    except OSError as exc:
        raise RunSessionError(f"cannot start development session: {exc}") from exc
    return int(completed.returncode)


def _validated_arguments(values: Sequence[str], *, label: str) -> tuple[str, ...]:
    if len(values) > _MAX_FORWARDED_ARGS:
        raise RunSessionError(f"at most {_MAX_FORWARDED_ARGS} {label}s are allowed")
    result: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise RunSessionError(f"{label} must be a string")
        if len(value) > _MAX_ARGUMENT_LENGTH:
            raise RunSessionError(
                f"{label} must be at most {_MAX_ARGUMENT_LENGTH} characters"
            )
        if "\x00" in value:
            raise RunSessionError(f"{label} must not contain NUL characters")
        result.append(value)
    return tuple(result)


def _parse_environment_overrides(values: Iterable[str]) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for raw in values:
        if "=" not in raw:
            raise RunSessionError("environment overrides must use NAME=VALUE")
        key, value = raw.split("=", 1)
        if not key:
            raise RunSessionError("environment override name must not be empty")
        if key in overrides:
            raise RunSessionError(f"duplicate environment override: {key}")
        ProjectManifest.validate_environment_pair(key, value, label="run override")
        overrides[key] = value
    return overrides


def _require_inside_project(root: Path, path: Path, *, label: str) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise RunSessionError(f"{label} resolved outside the project") from exc


def _diagnostic_summary(diagnostic: ProjectDiagnostic) -> str:
    location = f" [{diagnostic.path}]" if diagnostic.path else ""
    return f"{diagnostic.code}: {diagnostic.message}{location}"
