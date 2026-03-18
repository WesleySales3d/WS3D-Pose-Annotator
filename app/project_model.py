"""Project persistence model."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .annotation_model import FrameAnnotation, KeypointState


def _migrate_center_shoulder(left: KeypointState, right: KeypointState) -> KeypointState:
    candidates = [state for state in (left, right) if state.v > 0]
    if len(candidates) == 2:
        return KeypointState(
            x=(left.x + right.x) / 2,
            y=(left.y + right.y) / 2,
            v=2 if left.v == 2 or right.v == 2 else 1,
            contact=None,
        )
    if len(candidates) == 1 and candidates[0].v == 2:
        return KeypointState(x=candidates[0].x, y=candidates[0].y, v=2, contact=None)
    return KeypointState()


def _migrate_pose23_annotation(annotation: FrameAnnotation) -> FrameAnnotation:
    if len(annotation.keypoints) != 23:
        return annotation
    old = annotation.keypoints
    return FrameAnnotation(
        frame_index=annotation.frame_index,
        timestamp=annotation.timestamp,
        width=annotation.width,
        height=annotation.height,
        keypoints=[
            old[0].clone(),
            old[1].clone(),
            old[2].clone(),
            old[3].clone(),
            old[4].clone(),
            _migrate_center_shoulder(old[5], old[7]),
            old[6].clone(),
            old[8].clone(),
            old[9].clone(),
            old[10].clone(),
            old[11].clone(),
            old[12].clone(),
            KeypointState(),
            old[13].clone(),
            old[14].clone(),
            old[15].clone(),
            old[16].clone(),
            old[17].clone(),
            old[18].clone(),
            old[19].clone(),
            old[20].clone(),
            old[21].clone(),
            old[22].clone(),
        ],
    )


def _migrate_pose23_item(item: "ProjectItemData") -> "ProjectItemData":
    item.annotations = {
        frame_index: _migrate_pose23_annotation(annotation)
        for frame_index, annotation in item.annotations.items()
    }
    return item


@dataclass
class VideoMetadata:
    """Metadata extracted from a media file."""

    video_path: str
    width: int
    height: int
    fps: float
    duration: float
    total_frames: int

    def to_dict(self) -> dict:
        return {
            "video_path": self.video_path,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "duration": self.duration,
            "total_frames": self.total_frames,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "VideoMetadata":
        return cls(
            video_path=str(data["video_path"]),
            width=int(data["width"]),
            height=int(data["height"]),
            fps=float(data["fps"]),
            duration=float(data["duration"]),
            total_frames=int(data["total_frames"]),
        )


@dataclass
class ProjectItemData:
    """A single imported media item inside a project."""

    item_id: str
    name: str
    media_path: str
    media_metadata: VideoMetadata
    media_kind: str
    include_in_export: bool = True
    annotations: dict[int, FrameAnnotation] = field(default_factory=dict)
    visited_frames: set[int] = field(default_factory=set)
    cache_dir: str | None = None

    @classmethod
    def create(
        cls,
        media_path: str,
        media_metadata: VideoMetadata,
        media_kind: str,
        cache_dir: str | None = None,
        *,
        name: str | None = None,
        item_id: str | None = None,
    ) -> "ProjectItemData":
        resolved = str(Path(media_path).resolve())
        return cls(
            item_id=item_id or uuid.uuid4().hex,
            name=name or Path(resolved).name,
            media_path=resolved,
            media_metadata=media_metadata,
            media_kind=media_kind,
            include_in_export=True,
            cache_dir=cache_dir,
        )

    def get_annotation(self, frame_index: int) -> FrameAnnotation | None:
        annotation = self.annotations.get(frame_index)
        return annotation.clone() if annotation else None

    def upsert_annotation(self, annotation: FrameAnnotation) -> None:
        self.annotations[annotation.frame_index] = annotation.clone()

    def remove_annotation(self, frame_index: int) -> None:
        self.annotations.pop(frame_index, None)

    def to_dict(self) -> dict:
        return {
            "item_id": self.item_id,
            "name": self.name,
            "media_path": self.media_path,
            "media_kind": self.media_kind,
            "include_in_export": self.include_in_export,
            "media_metadata": self.media_metadata.to_dict(),
            "annotations": {
                str(frame_index): annotation.to_dict()
                for frame_index, annotation in sorted(self.annotations.items())
            },
            "visited_frames": sorted(self.visited_frames),
            "cache_dir": self.cache_dir,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectItemData":
        item = cls(
            item_id=str(data.get("item_id") or uuid.uuid4().hex),
            name=str(data.get("name") or Path(str(data["media_path"])).name),
            media_path=str(data["media_path"]),
            media_metadata=VideoMetadata.from_dict(data["media_metadata"]),
            media_kind=str(data.get("media_kind", "video")),
            include_in_export=bool(data.get("include_in_export", True)),
            cache_dir=data.get("cache_dir"),
        )
        item.annotations = {
            int(frame_index): FrameAnnotation.from_dict(annotation)
            for frame_index, annotation in data.get("annotations", {}).items()
        }
        item.visited_frames = {int(frame_index) for frame_index in data.get("visited_frames", [])}
        return item


@dataclass
class ProjectData:
    """All persisted application state."""

    version: int = 4
    skeleton_name: str = "POSE23"
    items: list[ProjectItemData] = field(default_factory=list)
    active_item_id: str | None = None
    ui_state: dict = field(default_factory=dict)

    def reset(self) -> None:
        self.version = 4
        self.skeleton_name = "POSE23"
        self.items.clear()
        self.active_item_id = None
        self.ui_state.clear()

    @property
    def current_item(self) -> ProjectItemData | None:
        if not self.items:
            return None
        if self.active_item_id:
            for item in self.items:
                if item.item_id == self.active_item_id:
                    return item
        self.active_item_id = self.items[0].item_id
        return self.items[0]

    def get_item(self, item_id: str) -> ProjectItemData | None:
        for item in self.items:
            if item.item_id == item_id:
                return item
        return None

    def set_active_item(self, item_id: str) -> None:
        if self.get_item(item_id):
            self.active_item_id = item_id

    def add_item(self, item: ProjectItemData, *, make_active: bool = True) -> ProjectItemData:
        existing_ids = {existing.item_id for existing in self.items}
        if item.item_id in existing_ids:
            item.item_id = uuid.uuid4().hex
        self.items.append(item)
        if make_active or not self.active_item_id:
            self.active_item_id = item.item_id
        return item

    def add_media(
        self,
        media_path: str,
        media_metadata: VideoMetadata,
        media_kind: str,
        cache_dir: str | None = None,
        *,
        name: str | None = None,
        item_id: str | None = None,
        make_active: bool = True,
    ) -> ProjectItemData:
        item = ProjectItemData.create(
            media_path=media_path,
            media_metadata=media_metadata,
            media_kind=media_kind,
            cache_dir=cache_dir,
            name=name,
            item_id=item_id,
        )
        return self.add_item(item, make_active=make_active)

    def merge_project(self, other: "ProjectData") -> list[ProjectItemData]:
        merged_items: list[ProjectItemData] = []
        for other_item in other.items:
            cloned = ProjectItemData.from_dict(other_item.to_dict())
            self.add_item(cloned, make_active=False)
            merged_items.append(cloned)
        if merged_items and not self.active_item_id:
            self.active_item_id = merged_items[0].item_id
        return merged_items

    def remove_item(self, item_id: str) -> ProjectItemData | None:
        for index, item in enumerate(self.items):
            if item.item_id != item_id:
                continue
            removed = self.items.pop(index)
            if self.active_item_id == item_id:
                self.active_item_id = self.items[min(index, len(self.items) - 1)].item_id if self.items else None
            return removed
        return None

    @property
    def video_path(self) -> str | None:
        return self.current_item.media_path if self.current_item else None

    @video_path.setter
    def video_path(self, value: str | None) -> None:
        if self.current_item and value is not None:
            self.current_item.media_path = value

    @property
    def video_metadata(self) -> VideoMetadata | None:
        return self.current_item.media_metadata if self.current_item else None

    @video_metadata.setter
    def video_metadata(self, value: VideoMetadata | None) -> None:
        if self.current_item and value is not None:
            self.current_item.media_metadata = value

    @property
    def annotations(self) -> dict[int, FrameAnnotation]:
        return self.current_item.annotations if self.current_item else {}

    @annotations.setter
    def annotations(self, value: dict[int, FrameAnnotation]) -> None:
        if self.current_item is not None:
            self.current_item.annotations = value

    @property
    def visited_frames(self) -> set[int]:
        return self.current_item.visited_frames if self.current_item else set()

    @visited_frames.setter
    def visited_frames(self, value: set[int]) -> None:
        if self.current_item is not None:
            self.current_item.visited_frames = value

    @property
    def cache_dir(self) -> str | None:
        return self.current_item.cache_dir if self.current_item else None

    @cache_dir.setter
    def cache_dir(self, value: str | None) -> None:
        if self.current_item is not None:
            self.current_item.cache_dir = value

    def get_annotation(self, frame_index: int) -> FrameAnnotation | None:
        return self.current_item.get_annotation(frame_index) if self.current_item else None

    def upsert_annotation(self, annotation: FrameAnnotation) -> None:
        if self.current_item is not None:
            self.current_item.upsert_annotation(annotation)

    def remove_annotation(self, frame_index: int) -> None:
        if self.current_item is not None:
            self.current_item.remove_annotation(frame_index)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "skeleton_name": self.skeleton_name,
            "active_item_id": self.active_item_id,
            "items": [item.to_dict() for item in self.items],
            "ui_state": self.ui_state,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectData":
        if "items" in data:
            version = int(data.get("version", 2))
            project = cls(
                version=version,
                skeleton_name=str(data.get("skeleton_name", "POSE23")),
                active_item_id=data.get("active_item_id"),
                ui_state=dict(data.get("ui_state", {})),
            )
            project.items = [ProjectItemData.from_dict(item_data) for item_data in data.get("items", [])]
            if version < 4 and project.skeleton_name == "POSE23":
                project.items = [_migrate_pose23_item(item) for item in project.items]
            if not project.active_item_id and project.items:
                project.active_item_id = project.items[0].item_id
            return project

        project = cls(
            version=int(data.get("version", 1)),
            skeleton_name=str(data.get("skeleton_name", "POSE23")),
            ui_state=dict(data.get("ui_state", {})),
        )
        legacy_metadata = VideoMetadata.from_dict(data["video_metadata"]) if data.get("video_metadata") else None
        legacy_path = data.get("video_path")
        if legacy_metadata and legacy_path:
            media_kind = "image" if legacy_metadata.total_frames <= 1 else "video"
            item = ProjectItemData.create(
                media_path=str(legacy_path),
                media_metadata=legacy_metadata,
                media_kind=media_kind,
                cache_dir=data.get("cache_dir"),
                name=Path(str(legacy_path)).name,
            )
            item.annotations = {
                int(frame_index): FrameAnnotation.from_dict(annotation)
                for frame_index, annotation in data.get("annotations", {}).items()
            }
            item.visited_frames = {int(frame_index) for frame_index in data.get("visited_frames", [])}
            if project.skeleton_name == "POSE23":
                item = _migrate_pose23_item(item)
            project.add_item(item)
        return project

    def save(self, path: str | Path) -> None:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str | Path) -> "ProjectData":
        project_path = Path(path)
        data = json.loads(project_path.read_text(encoding="utf-8"))
        return cls.from_dict(data)

