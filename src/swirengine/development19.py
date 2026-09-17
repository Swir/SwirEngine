from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any

from .project19 import ProjectManifest, ProjectManifestError

_ENVIRONMENT_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
Runner = Callable[..., Any]


class ProjectRunError(RuntimeError):
    """Raised when a development session cannot be planned or executed safely."""


@dataclass(slots=True, frozen=True)
class ProjectRunPlan:
    project_root: Path
    command: tuple[str, ...]
    entrypoint: str
    arguments: tuple[str, ...]
    environment_overrides: Mapping[str, str]
    inherit_environment: bool
    manifest_fingerprint: str
    configuration_fingerprint: str

    def to_dict(self, *, include_environment_values: bool = False) -> dict[str, object]:
        environment: object
        if include_environment_values:
            environment = dict(sorted(self.environment_overrides.items()))
        else:
            environment = sorted(self.environment_overrides)
        return {
            "entrypoint": self.entrypoint,
            "arguments": list(self.arguments),
            "environment": environment,
            "inherit_environment": self.inherit_environment,
            "manifest_fingerprint": self.manifest_fingerprint,
            "configuration_fingerprint": self.configuration_fingerprint,
        }


@dataclass(slots=True, frozen=True)
class ProjectRunResult:
    plan: ProjectRunPlan
    returncode: int


class DevelopmentRunner:
    """Plan and execute manifest-driven project development sessions without a shell."""

    def __init__(self, manifest: ProjectManifest) -> None:
        self.manifest = manifest

    @classmethod
    def load(cls, project: str | Path = ".") -> DevelopmentRunner:
        return cls(ProjectManifest.load(project))

    def plan(
        self,
        *,
        extra_arguments: Sequence[str] = (),
        environment_overrides: Mapping[str, str] | None = None,
        inherit_environment: bool | None = None,
        python_executable: str | Path | None = None,
    ) -> ProjectRunPlan:
        run = self.manifest.run
        entrypoint_path = self.manifest.root / PurePosixPath(run.entrypoint)
        if not entrypoint_path.is_file():
            raise ProjectRunError(f"development entrypoint does not exist: {run.entrypoint}")

        extra = _validate_arguments(extra_arguments, label="extra arguments")
        overrides = dict(run.environment)
        if environment_overrides:
            overrides.update(_validate_environment(environment_overrides))
        inherited = run.inherit_environment if inherit_environment is None else bool(inherit_environment)
        interpreter = str(Path(python_executable or sys.executable).expanduser().resolve())
        arguments = (*run.arguments, *extra)
        command = (interpreter, run.entrypoint, *arguments)
        fingerprint_payload = {
            "manifest_fingerprint": self.manifest.fingerprint,
            "entrypoint": run.entrypoint,
            "arguments": list(arguments),
            "environment": dict(sorted(overrides.items())),
            "inherit_environment": inherited,
        }
        fingerprint = hashlib.sha256(
            json.dumps(
                fingerprint_payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("utf-8")
        ).hexdigest()
        return ProjectRunPlan(
            project_root=self.manifest.root,
            command=command,
            entrypoint=run.entrypoint,
            arguments=arguments,
            environment_overrides=MappingProxyType(dict(sorted(overrides.items()))),
            inherit_environment=inherited,
            manifest_fingerprint=self.manifest.fingerprint,
            configuration_fingerprint=fingerprint,
        )

    def execute(
        self,
        plan: ProjectRunPlan,
        *,
        runner: Runner = subprocess.run,
    ) -> ProjectRunResult:
        if plan.project_root != self.manifest.root:
            raise ProjectRunError("run plan belongs to a different project root")
        environment = dict(os.environ) if plan.inherit_environment else {}
        environment.update(plan.environment_overrides)
        completed = runner(
            plan.command,
            cwd=plan.project_root,
            env=environment,
            check=False,
        )
        return ProjectRunResult(plan=plan, returncode=int(completed.returncode))


def parse_environment_assignments(values: Sequence[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for value in values:
        if not isinstance(value, str) or "=" not in value:
            raise ProjectManifestError("environment overrides must use NAME=VALUE")
        key, content = value.split("=", 1)
        parsed.update(_validate_environment({key: content}))
    return parsed


def _validate_arguments(values: Sequence[str], *, label: str) -> tuple[str, ...]:
    if len(values) > 128:
        raise ProjectRunError(f"{label} must contain at most 128 values")
    validated: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise ProjectRunError(f"{label} must contain strings")
        if len(value) > 512:
            raise ProjectRunError(f"{label} values must be at most 512 characters")
        if "\x00" in value:
            raise ProjectRunError(f"{label} must not contain NUL characters")
        validated.append(value)
    return tuple(validated)


def _validate_environment(values: Mapping[str, str]) -> dict[str, str]:
    if len(values) > 64:
        raise ProjectRunError("environment overrides must contain at most 64 variables")
    validated: dict[str, str] = {}
    for key, value in values.items():
        if not isinstance(key, str) or not _ENVIRONMENT_KEY_RE.fullmatch(key):
            raise ProjectRunError(f"invalid environment variable name: {key!r}")
        if not isinstance(value, str):
            raise ProjectRunError(f"environment value for {key} must be a string")
        if len(value) > 1024:
            raise ProjectRunError(f"environment value for {key} must be at most 1024 characters")
        if "\x00" in value:
            raise ProjectRunError(f"environment value for {key} must not contain NUL characters")
        validated[key] = value
    return validated
