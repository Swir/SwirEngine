from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .animation_state_machine22 import AnimationStateMachine22
from .editor_animation_state_machine22 import (
    ANIMATION_MACHINE_SUFFIX22,
    AnimationMachineDocument22,
    AnimationMachineEditorSession22,
    AnimationMachineProjectStore22,
    AnimationStateNode22,
)
from .editor_animation_state_machine_frontend22 import (
    AnimationMachineEditorFrame22,
    AnimationMachinePanelController22,
)
from .graphics.skeletal import SkeletalAnimationClip3D, Skeleton3D


@dataclass(frozen=True, slots=True)
class AnimationMachineWorkspaceSnapshot22:
    assets: tuple[str, ...]
    active_asset: str | None
    dirty: bool
    preview_bound: bool


class AnimationMachineWorkspace22:
    """Project-level M5 workspace joining asset discovery, editing and runtime preview.

    The workspace is intentionally toolkit-neutral. SwirEditor can keep one instance for
    the whole project while individual graph windows are opened and closed. Asset names
    are always resolved through ``AnimationMachineProjectStore22`` so creator input never
    escapes ``assets/animation_machines``.
    """

    def __init__(self, project_root: Path | str) -> None:
        self.project_root = Path(project_root).resolve()
        self.store = AnimationMachineProjectStore22(self.project_root)
        self._session: AnimationMachineEditorSession22 | None = None
        self._controller: AnimationMachinePanelController22 | None = None
        self._skeleton: Skeleton3D | None = None
        self._clips: dict[str, SkeletalAnimationClip3D] = {}

    @property
    def active_session(self) -> AnimationMachineEditorSession22:
        if self._session is None:
            raise RuntimeError("no animation machine asset is open")
        return self._session

    @property
    def controller(self) -> AnimationMachinePanelController22:
        if self._controller is None:
            raise RuntimeError("no animation machine asset is open")
        return self._controller

    @property
    def dirty(self) -> bool:
        return bool(self._session is not None and self._session.dirty)

    @property
    def preview_bound(self) -> bool:
        return self._skeleton is not None and bool(self._clips)

    def snapshot(self) -> AnimationMachineWorkspaceSnapshot22:
        return AnimationMachineWorkspaceSnapshot22(
            assets=self.discover(),
            active_asset=None if self._session is None else self._session.asset_name,
            dirty=self.dirty,
            preview_bound=self.preview_bound,
        )

    def discover(self) -> tuple[str, ...]:
        root = self.store.asset_root
        if not root.exists():
            return ()
        resolved_root = root.resolve()
        assets: list[str] = []
        for path in root.rglob(f"*{ANIMATION_MACHINE_SUFFIX22}"):
            if not path.is_file():
                continue
            try:
                resolved = path.resolve()
                relative = resolved.relative_to(resolved_root).as_posix()
                # Re-run the store's confinement/suffix validation for discovered files.
                self.store.path_for(relative)
            except (OSError, ValueError):
                continue
            assets.append(relative)
        return tuple(sorted(set(assets), key=lambda item: (item.casefold(), item)))

    def create(
        self,
        asset_name: str,
        document: AnimationMachineDocument22 | None = None,
    ) -> AnimationMachineEditorFrame22:
        if document is None:
            document = AnimationMachineDocument22(
                states=(AnimationStateNode22("Idle", clip="idle"),),
                initial="Idle",
            )
        # Validate before replacing the active editor session.
        self.store.path_for(asset_name)
        self._session = AnimationMachineEditorSession22.create(
            self.project_root,
            asset_name,
            document,
        )
        self._controller = AnimationMachinePanelController22(self._session)
        return self._controller.frame()

    def open(self, asset_name: str) -> AnimationMachineEditorFrame22:
        self._session = AnimationMachineEditorSession22.open(self.project_root, asset_name)
        self._controller = AnimationMachinePanelController22(self._session)
        return self._controller.frame()

    def save(self) -> AnimationMachineEditorFrame22:
        return self.controller.save()

    def bind_preview_resources(
        self,
        skeleton: Skeleton3D,
        clips: Mapping[str, SkeletalAnimationClip3D],
    ) -> None:
        if not isinstance(skeleton, Skeleton3D):
            raise TypeError("skeleton must be Skeleton3D")
        bound = dict(clips)
        if not bound:
            raise ValueError("at least one skeletal animation clip is required")
        if any(not isinstance(clip, SkeletalAnimationClip3D) for clip in bound.values()):
            raise TypeError("preview clips must be SkeletalAnimationClip3D")
        self._skeleton = skeleton
        self._clips = bound

    def clear_preview_resources(self) -> None:
        if self._controller is not None:
            self._controller.stop_preview()
        self._skeleton = None
        self._clips = {}

    def validate_runtime(self) -> tuple[str, ...]:
        if self._skeleton is None or not self._clips:
            return ("preview resources are not bound",)
        return self.controller.validate_runtime(self._skeleton, self._clips)

    def start_preview(self) -> AnimationMachineEditorFrame22:
        if self._skeleton is None or not self._clips:
            raise RuntimeError("preview resources are not bound")
        return self.controller.start_preview(self._skeleton, self._clips)

    def compile_active(self) -> AnimationStateMachine22:
        if self._skeleton is None or not self._clips:
            raise RuntimeError("preview resources are not bound")
        return self.active_session.compile(self._skeleton, self._clips)
