from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .graphics.skeletal import SkeletalAnimationClip3D, Skeleton3D

ANIMATION_RESOURCE_BINDINGS_FORMAT22 = "swir.animation-preview-resources.v1"
ANIMATION_RESOURCE_BINDINGS_SUFFIX22 = ".resources.json"


def _resource_ref(value: str, *, label: str) -> str:
    ref = str(value).strip()
    if not ref:
        raise ValueError(f"{label} cannot be empty")
    return ref


@dataclass(frozen=True, slots=True)
class AnimationPreviewResourceRefs22:
    """Serializable logical references used to rebuild a runtime preview binding.

    References deliberately stay loader-agnostic. A project/import pipeline supplies the
    resolver so animation graphs can point at imported skeletal resources without copying
    runtime objects or source-model data into ``.swiranimgraph`` assets.
    """

    skeleton: str
    clips: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        skeleton = _resource_ref(self.skeleton, label="skeleton resource reference")
        normalized: list[tuple[str, str]] = []
        seen: set[str] = set()
        for clip_id, resource_ref in self.clips:
            clip_name = _resource_ref(clip_id, label="clip id")
            if clip_name in seen:
                raise ValueError(f"duplicate animation clip id: {clip_name}")
            seen.add(clip_name)
            normalized.append(
                (
                    clip_name,
                    _resource_ref(resource_ref, label=f"clip resource reference ({clip_name})"),
                )
            )
        if not normalized:
            raise ValueError("at least one clip resource reference is required")
        object.__setattr__(self, "skeleton", skeleton)
        object.__setattr__(
            self,
            "clips",
            tuple(sorted(normalized, key=lambda item: (item[0].casefold(), item[0]))),
        )

    @classmethod
    def from_mapping(
        cls,
        skeleton: str,
        clips: Mapping[str, str],
    ) -> AnimationPreviewResourceRefs22:
        return cls(skeleton, tuple((str(name), str(ref)) for name, ref in clips.items()))

    @property
    def clips_by_id(self) -> dict[str, str]:
        return dict(self.clips)


def animation_preview_resource_refs_to_dict22(
    refs: AnimationPreviewResourceRefs22,
) -> dict[str, Any]:
    return {
        "format": ANIMATION_RESOURCE_BINDINGS_FORMAT22,
        "skeleton": refs.skeleton,
        "clips": {name: resource_ref for name, resource_ref in refs.clips},
    }


def animation_preview_resource_refs_from_dict22(
    payload: Mapping[str, Any],
) -> AnimationPreviewResourceRefs22:
    if payload.get("format") != ANIMATION_RESOURCE_BINDINGS_FORMAT22:
        raise ValueError("unsupported animation preview resource binding format")
    clips = payload.get("clips")
    if not isinstance(clips, Mapping):
        raise TypeError("animation preview resource clips must be an object")
    return AnimationPreviewResourceRefs22.from_mapping(
        str(payload.get("skeleton", "")),
        {str(name): str(resource_ref) for name, resource_ref in clips.items()},
    )


def animation_preview_resource_sidecar_path22(graph_path: Path | str) -> Path:
    path = Path(graph_path)
    return path.with_name(path.name + ANIMATION_RESOURCE_BINDINGS_SUFFIX22)


def save_animation_preview_resource_refs22(
    graph_path: Path | str,
    refs: AnimationPreviewResourceRefs22,
) -> Path:
    target = animation_preview_resource_sidecar_path22(graph_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            animation_preview_resource_refs_to_dict22(refs),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return target


def load_animation_preview_resource_refs22(
    graph_path: Path | str,
) -> AnimationPreviewResourceRefs22 | None:
    target = animation_preview_resource_sidecar_path22(graph_path)
    if not target.exists():
        return None
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise TypeError("animation preview resource binding root must be an object")
    return animation_preview_resource_refs_from_dict22(payload)


def clear_animation_preview_resource_refs22(graph_path: Path | str) -> None:
    target = animation_preview_resource_sidecar_path22(graph_path)
    try:
        target.unlink()
    except FileNotFoundError:
        pass


def resolve_animation_preview_resource_refs22(
    refs: AnimationPreviewResourceRefs22,
    resolver: Callable[[str], object],
) -> tuple[Skeleton3D, dict[str, SkeletalAnimationClip3D]]:
    skeleton = resolver(refs.skeleton)
    if not isinstance(skeleton, Skeleton3D):
        raise TypeError(f"resource {refs.skeleton!r} did not resolve to Skeleton3D")

    clips: dict[str, SkeletalAnimationClip3D] = {}
    for clip_id, resource_ref in refs.clips:
        clip = resolver(resource_ref)
        if not isinstance(clip, SkeletalAnimationClip3D):
            raise TypeError(
                f"resource {resource_ref!r} for clip {clip_id!r} did not resolve "
                "to SkeletalAnimationClip3D"
            )
        clips[clip_id] = clip
    return skeleton, clips
