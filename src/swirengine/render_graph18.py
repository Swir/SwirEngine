from __future__ import annotations

import hashlib
import heapq
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType


def _name(value: str, *, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    result = value.strip()
    if not result:
        raise ValueError(f"{label} must not be empty")
    if len(result) > 128:
        raise ValueError(f"{label} must contain at most 128 characters")
    return result


def _positive_int(value: int, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if value < 1:
        raise ValueError(f"{label} must be >= 1")
    return value


def _nonnegative_int(value: int, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if value < 0:
        raise ValueError(f"{label} must be >= 0")
    return value


def _names(values: Iterable[str], *, label: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{label} must be an iterable of names, not a string")
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _name(value, label=f"{label} entry")
        if normalized in seen:
            raise ValueError(f"duplicate {label} entry: {normalized}")
        seen.add(normalized)
        result.append(normalized)
    return tuple(result)


class RenderGraphError(RuntimeError):
    """Stable creator-facing render-graph validation/compile failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class RenderResourceSpec:
    name: str
    transient: bool
    external: bool
    size_bytes: int
    sequence: int


@dataclass(frozen=True, slots=True)
class RenderPassSpec:
    name: str
    reads: tuple[str, ...]
    writes: tuple[str, ...]
    depends_on: tuple[str, ...]
    side_effect: bool
    priority: int
    sequence: int


@dataclass(frozen=True, slots=True)
class ResourceLifetime:
    name: str
    first_pass: int
    last_pass: int
    transient: bool
    external: bool
    size_bytes: int
    alias_slot: int | None

    @property
    def span(self) -> int:
        return self.last_pass - self.first_pass + 1


@dataclass(frozen=True, slots=True)
class AliasSlot:
    slot: int
    size_bytes: int
    resources: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RenderGraphDiagnostics:
    authored_passes: int
    active_passes: int
    culled_passes: int
    resources: int
    active_resources: int
    dependency_edges: int
    transient_resources: int
    transient_unaliased_bytes: int
    transient_reserved_bytes: int
    transient_alias_savings_bytes: int
    transient_peak_live_bytes: int
    alias_slots: int

    def portable(self) -> Mapping[str, int]:
        return MappingProxyType(
            {
                "authored_passes": self.authored_passes,
                "active_passes": self.active_passes,
                "culled_passes": self.culled_passes,
                "resources": self.resources,
                "active_resources": self.active_resources,
                "dependency_edges": self.dependency_edges,
                "transient_resources": self.transient_resources,
                "transient_unaliased_bytes": self.transient_unaliased_bytes,
                "transient_reserved_bytes": self.transient_reserved_bytes,
                "transient_alias_savings_bytes": self.transient_alias_savings_bytes,
                "transient_peak_live_bytes": self.transient_peak_live_bytes,
                "alias_slots": self.alias_slots,
            }
        )


@dataclass(frozen=True, slots=True)
class RenderGraphPlan:
    passes: tuple[str, ...]
    culled_passes: tuple[str, ...]
    outputs: tuple[str, ...]
    dependencies: Mapping[str, tuple[str, ...]]
    lifetimes: Mapping[str, ResourceLifetime]
    alias_slots: tuple[AliasSlot, ...]
    diagnostics: RenderGraphDiagnostics
    fingerprint: str

    def portable(self) -> Mapping[str, object]:
        lifetimes = {
            name: {
                "first_pass": item.first_pass,
                "last_pass": item.last_pass,
                "transient": item.transient,
                "external": item.external,
                "size_bytes": item.size_bytes,
                "alias_slot": item.alias_slot,
            }
            for name, item in sorted(self.lifetimes.items())
        }
        return MappingProxyType(
            {
                "passes": list(self.passes),
                "culled_passes": list(self.culled_passes),
                "outputs": list(self.outputs),
                "dependencies": {
                    name: list(values) for name, values in sorted(self.dependencies.items())
                },
                "lifetimes": lifetimes,
                "alias_slots": [
                    {
                        "slot": slot.slot,
                        "size_bytes": slot.size_bytes,
                        "resources": list(slot.resources),
                    }
                    for slot in self.alias_slots
                ],
                "diagnostics": dict(self.diagnostics.portable()),
                "fingerprint": self.fingerprint,
            }
        )


class RenderGraphBuilder:
    """Compile a deterministic renderer-independent pass/resource plan."""

    def __init__(self, *, max_passes: int = 2048, max_resources: int = 4096) -> None:
        self.max_passes = _positive_int(max_passes, label="max_passes")
        self.max_resources = _positive_int(max_resources, label="max_resources")
        self._resources: dict[str, RenderResourceSpec] = {}
        self._passes: dict[str, RenderPassSpec] = {}
        self._outputs: set[str] = set()
        self._next_resource_sequence = 0
        self._next_pass_sequence = 0

    @property
    def resources(self) -> tuple[RenderResourceSpec, ...]:
        return tuple(self._resources.values())

    @property
    def passes(self) -> tuple[RenderPassSpec, ...]:
        return tuple(self._passes.values())

    def add_resource(
        self,
        name: str,
        *,
        transient: bool = False,
        external: bool = False,
        size_bytes: int = 0,
    ) -> RenderResourceSpec:
        normalized = _name(name, label="resource name")
        if normalized in self._resources:
            raise RenderGraphError("duplicate-resource", f"resource already exists: {normalized}")
        if len(self._resources) >= self.max_resources:
            raise RenderGraphError("resource-limit", "render graph resource limit reached")
        if not isinstance(transient, bool):
            raise TypeError("transient must be a boolean")
        if not isinstance(external, bool):
            raise TypeError("external must be a boolean")
        if transient and external:
            raise ValueError("a resource cannot be both transient and external")
        spec = RenderResourceSpec(
            name=normalized,
            transient=transient,
            external=external,
            size_bytes=_nonnegative_int(size_bytes, label="size_bytes"),
            sequence=self._next_resource_sequence,
        )
        self._next_resource_sequence += 1
        self._resources[normalized] = spec
        return spec

    def add_pass(
        self,
        name: str,
        *,
        reads: Iterable[str] = (),
        writes: Iterable[str] = (),
        depends_on: Iterable[str] = (),
        side_effect: bool = False,
        priority: int = 0,
    ) -> RenderPassSpec:
        normalized = _name(name, label="pass name")
        if normalized in self._passes:
            raise RenderGraphError("duplicate-pass", f"pass already exists: {normalized}")
        if len(self._passes) >= self.max_passes:
            raise RenderGraphError("pass-limit", "render graph pass limit reached")
        read_names = _names(reads, label="read resource")
        write_names = _names(writes, label="write resource")
        dependency_names = _names(depends_on, label="pass dependency")
        overlap = set(read_names).intersection(write_names)
        if overlap:
            repeated = min(overlap)
            raise RenderGraphError(
                "in-place-resource",
                f"pass {normalized} cannot read and write the same resource: {repeated}",
            )
        for resource in (*read_names, *write_names):
            if resource not in self._resources:
                raise RenderGraphError(
                    "unknown-resource",
                    f"pass {normalized} references unknown resource: {resource}",
                )
        if normalized in dependency_names:
            raise RenderGraphError("self-dependency", f"pass cannot depend on itself: {normalized}")
        if not isinstance(side_effect, bool):
            raise TypeError("side_effect must be a boolean")
        if isinstance(priority, bool) or not isinstance(priority, int):
            raise TypeError("priority must be an integer")
        spec = RenderPassSpec(
            name=normalized,
            reads=read_names,
            writes=write_names,
            depends_on=dependency_names,
            side_effect=side_effect,
            priority=priority,
            sequence=self._next_pass_sequence,
        )
        self._next_pass_sequence += 1
        self._passes[normalized] = spec
        return spec

    def mark_output(self, resource: str) -> None:
        normalized = _name(resource, label="output resource")
        if normalized not in self._resources:
            raise RenderGraphError("unknown-output", f"unknown output resource: {normalized}")
        self._outputs.add(normalized)

    def unmark_output(self, resource: str) -> bool:
        normalized = _name(resource, label="output resource")
        if normalized not in self._resources:
            raise RenderGraphError("unknown-output", f"unknown output resource: {normalized}")
        existed = normalized in self._outputs
        self._outputs.discard(normalized)
        return existed

    def compile(self) -> RenderGraphPlan:
        writers = self._resolve_writers()
        dependencies = self._resolve_dependencies(writers)
        full_order = self._topological_order(dependencies)
        active = self._select_active_passes(dependencies, writers)
        pass_order = tuple(name for name in full_order if name in active)
        culled = tuple(
            spec.name
            for spec in sorted(self._passes.values(), key=lambda item: item.sequence)
            if spec.name not in active
        )
        lifetimes, alias_slots = self._build_lifetimes(pass_order)
        transient = [item for item in lifetimes.values() if item.transient]
        unaliased_bytes = sum(item.size_bytes for item in transient)
        reserved_bytes = sum(slot.size_bytes for slot in alias_slots)
        diagnostics = RenderGraphDiagnostics(
            authored_passes=len(self._passes),
            active_passes=len(pass_order),
            culled_passes=len(culled),
            resources=len(self._resources),
            active_resources=len(lifetimes),
            dependency_edges=sum(len(values) for values in dependencies.values()),
            transient_resources=len(transient),
            transient_unaliased_bytes=unaliased_bytes,
            transient_reserved_bytes=reserved_bytes,
            transient_alias_savings_bytes=max(0, unaliased_bytes - reserved_bytes),
            transient_peak_live_bytes=self._peak_live_bytes(transient, len(pass_order)),
            alias_slots=len(alias_slots),
        )
        dependency_view = MappingProxyType(
            {
                name: tuple(sorted(values, key=self._pass_sort_key))
                for name, values in dependencies.items()
            }
        )
        lifetime_view = MappingProxyType(dict(sorted(lifetimes.items())))
        outputs = tuple(sorted(self._outputs, key=self._resource_sort_key))
        fingerprint = self._fingerprint(
            pass_order,
            culled,
            outputs,
            dependency_view,
            lifetime_view,
            alias_slots,
            diagnostics,
        )
        return RenderGraphPlan(
            passes=pass_order,
            culled_passes=culled,
            outputs=outputs,
            dependencies=dependency_view,
            lifetimes=lifetime_view,
            alias_slots=alias_slots,
            diagnostics=diagnostics,
            fingerprint=fingerprint,
        )

    def _resolve_writers(self) -> dict[str, str]:
        writers: dict[str, str] = {}
        for spec in self._passes.values():
            for resource in spec.writes:
                previous = writers.get(resource)
                if previous is not None:
                    raise RenderGraphError(
                        "multiple-writers",
                        f"resource {resource} is written by both {previous} and {spec.name}",
                    )
                writers[resource] = spec.name
        return writers

    def _resolve_dependencies(self, writers: Mapping[str, str]) -> dict[str, set[str]]:
        dependencies: dict[str, set[str]] = {name: set() for name in self._passes}
        for spec in self._passes.values():
            for dependency in spec.depends_on:
                if dependency not in self._passes:
                    raise RenderGraphError(
                        "missing-pass-dependency",
                        f"pass {spec.name} depends on unknown pass: {dependency}",
                    )
                dependencies[spec.name].add(dependency)
            for resource in spec.reads:
                writer = writers.get(resource)
                if writer is None:
                    if not self._resources[resource].external:
                        message = (
                            f"pass {spec.name} reads internal resource without a writer: {resource}"
                        )
                        raise RenderGraphError("uninitialized-resource", message)
                    continue
                dependencies[spec.name].add(writer)
        for output in self._outputs:
            if output not in writers and not self._resources[output].external:
                raise RenderGraphError(
                    "uninitialized-output",
                    f"internal output resource has no writer: {output}",
                )
        return dependencies

    def _topological_order(self, dependencies: Mapping[str, set[str]]) -> tuple[str, ...]:
        indegree = {name: len(values) for name, values in dependencies.items()}
        dependants: dict[str, list[str]] = {name: [] for name in dependencies}
        for name, values in dependencies.items():
            for dependency in values:
                dependants[dependency].append(name)
        ready: list[tuple[int, int, str]] = []
        for name, count in indegree.items():
            if count == 0:
                heapq.heappush(ready, self._pass_sort_key(name))
        order: list[str] = []
        while ready:
            _, _, name = heapq.heappop(ready)
            order.append(name)
            for dependant in dependants[name]:
                indegree[dependant] -= 1
                if indegree[dependant] == 0:
                    heapq.heappush(ready, self._pass_sort_key(dependant))
        if len(order) != len(self._passes):
            blocked = tuple(
                sorted(
                    (name for name, count in indegree.items() if count),
                    key=self._pass_sort_key,
                )
            )
            raise RenderGraphError(
                "dependency-cycle",
                f"render graph contains a dependency cycle involving: {', '.join(blocked)}",
            )
        return tuple(order)

    def _select_active_passes(
        self,
        dependencies: Mapping[str, set[str]],
        writers: Mapping[str, str],
    ) -> set[str]:
        roots = {spec.name for spec in self._passes.values() if spec.side_effect}
        roots.update(writers[resource] for resource in self._outputs if resource in writers)
        if not roots:
            return set(self._passes)
        active: set[str] = set()
        pending = list(roots)
        while pending:
            name = pending.pop()
            if name in active:
                continue
            active.add(name)
            pending.extend(dependencies[name])
        return active

    def _build_lifetimes(
        self,
        pass_order: tuple[str, ...],
    ) -> tuple[dict[str, ResourceLifetime], tuple[AliasSlot, ...]]:
        uses: dict[str, list[int]] = {}
        for index, name in enumerate(pass_order):
            spec = self._passes[name]
            for resource in (*spec.reads, *spec.writes):
                uses.setdefault(resource, []).append(index)
        provisional: dict[str, ResourceLifetime] = {}
        for resource, indices in uses.items():
            spec = self._resources[resource]
            provisional[resource] = ResourceLifetime(
                name=resource,
                first_pass=min(indices),
                last_pass=max(indices),
                transient=spec.transient,
                external=spec.external,
                size_bytes=spec.size_bytes,
                alias_slot=None,
            )
        transient = sorted(
            (item for item in provisional.values() if item.transient),
            key=lambda item: (item.first_pass, self._resources[item.name].sequence, item.name),
        )
        slot_sizes: list[int] = []
        slot_resources: list[list[str]] = []
        active_slots: list[tuple[int, int]] = []
        free_slots: list[int] = []
        for lifetime in transient:
            while active_slots and active_slots[0][0] < lifetime.first_pass:
                _, slot = heapq.heappop(active_slots)
                heapq.heappush(free_slots, slot)
            if free_slots:
                selected = heapq.heappop(free_slots)
                slot_sizes[selected] = max(slot_sizes[selected], lifetime.size_bytes)
                slot_resources[selected].append(lifetime.name)
            else:
                selected = len(slot_sizes)
                slot_sizes.append(lifetime.size_bytes)
                slot_resources.append([lifetime.name])
            heapq.heappush(active_slots, (lifetime.last_pass, selected))
            provisional[lifetime.name] = ResourceLifetime(
                name=lifetime.name,
                first_pass=lifetime.first_pass,
                last_pass=lifetime.last_pass,
                transient=True,
                external=False,
                size_bytes=lifetime.size_bytes,
                alias_slot=selected,
            )
        aliases = tuple(
            AliasSlot(slot=index, size_bytes=slot_sizes[index], resources=tuple(resources))
            for index, resources in enumerate(slot_resources)
        )
        return provisional, aliases

    @staticmethod
    def _peak_live_bytes(lifetimes: list[ResourceLifetime], pass_count: int) -> int:
        if pass_count == 0 or not lifetimes:
            return 0
        deltas = [0] * (pass_count + 1)
        for lifetime in lifetimes:
            deltas[lifetime.first_pass] += lifetime.size_bytes
            if lifetime.last_pass + 1 < len(deltas):
                deltas[lifetime.last_pass + 1] -= lifetime.size_bytes
        peak = 0
        live = 0
        for index in range(pass_count):
            live += deltas[index]
            peak = max(peak, live)
        return peak

    def _pass_sort_key(self, name: str) -> tuple[int, int, str]:
        spec = self._passes[name]
        return (-spec.priority, spec.sequence, spec.name)

    def _resource_sort_key(self, name: str) -> tuple[int, str]:
        spec = self._resources[name]
        return (spec.sequence, spec.name)

    @staticmethod
    def _fingerprint(
        pass_order: tuple[str, ...],
        culled: tuple[str, ...],
        outputs: tuple[str, ...],
        dependencies: Mapping[str, tuple[str, ...]],
        lifetimes: Mapping[str, ResourceLifetime],
        alias_slots: tuple[AliasSlot, ...],
        diagnostics: RenderGraphDiagnostics,
    ) -> str:
        payload = {
            "version": 1,
            "passes": list(pass_order),
            "culled": list(culled),
            "outputs": list(outputs),
            "dependencies": {
                name: list(values) for name, values in sorted(dependencies.items())
            },
            "lifetimes": {
                name: [
                    value.first_pass,
                    value.last_pass,
                    value.transient,
                    value.external,
                    value.size_bytes,
                    value.alias_slot,
                ]
                for name, value in sorted(lifetimes.items())
            },
            "alias_slots": [
                [slot.slot, slot.size_bytes, list(slot.resources)] for slot in alias_slots
            ],
            "diagnostics": dict(diagnostics.portable()),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
