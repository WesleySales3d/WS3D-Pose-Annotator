"""Project persistence model."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .annotation_model import FrameAnnotation


@dataclass
class VideoMetadata:
    """Metadata extracted from a video file."""

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
class ProjectData:
    """All persisted application state."""

    version: int = 1
    video_path: str | None = None
    video_metadata: VideoMetadata | None = None
    skeleton_name: str = "POSE23"
    annotations: dict[int, FrameAnnotation] = field(default_factory=dict)
    visited_frames: set[int] = field(default_factory=set)
    ui_state: dict = field(default_factory=dict)
    cache_dir: str | None = None

    def reset(self) -> None:
        self.version = 1
        self.video_path = None
        self.video_metadata = None
        self.skeleton_name = "POSE23"
        self.annotations.clear()
        self.visited_frames.clear()
        self.ui_state.clear()
        self.cache_dir = None

    def get_annotation(self, frame_index: int) -> FrameAnnotation | None:
        annotation = self.annotations.get(frame_index)
        return annotation.clone() if annotation else None

    def upsert_annotation(self, annotation: FrameAnnotation) -> None:
        self.annotations[annotation.frame_index] = annotation.clone()

    def remove_annotation(self, frame_index: int) -> None:
        self.annotations.pop(frame_index, None)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "video_path": self.video_path,
            "video_metadata": self.video_metadata.to_dict() if self.video_metadata else None,
            "skeleton_name": self.skeleton_name,
            "annotations": {
                str(frame_index): annotation.to_dict()
                for frame_index, annotation in sorted(self.annotations.items())
            },
            "visited_frames": sorted(self.visited_frames),
            "ui_state": self.ui_state,
            "cache_dir": self.cache_dir,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectData":
        project = cls(
            version=int(data.get("version", 1)),
            video_path=data.get("video_path"),
            video_metadata=VideoMetadata.from_dict(data["video_metadata"])
            if data.get("video_metadata")
            else None,
            skeleton_name=str(data.get("skeleton_name", "POSE23")),
            ui_state=dict(data.get("ui_state", {})),
            cache_dir=data.get("cache_dir"),
        )
        project.annotations = {
            int(frame_index): FrameAnnotation.from_dict(annotation)
            for frame_index, annotation in data.get("annotations", {}).items()
        }
        project.visited_frames = {int(frame_index) for frame_index in data.get("visited_frames", [])}
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
