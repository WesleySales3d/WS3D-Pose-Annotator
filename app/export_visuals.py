"""Export rendered annotation overlays as image sequences or video."""

from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen

from .annotation_model import FrameAnnotation
from .ffmpeg_utils import encode_image_sequence_to_video
from .project_model import ProjectData
from .skeletons import SkeletonDefinition
from .video_manager import VideoManager


def _keypoint_color(visibility_value: int) -> QColor:
    if visibility_value == 2:
        return QColor("#ff6b6b")
    if visibility_value == 1:
        return QColor("#ffd166")
    return QColor("#8f949e")


def _effective_point_radius(width: int, height: int, point_radius: float) -> float:
    min_dimension = max(1, min(width, height))
    scale_factor = min(3.0, max(0.25, min_dimension / 1080.0))
    return max(1.0, point_radius * scale_factor)


def render_annotation_image(
    annotation: FrameAnnotation,
    skeleton: SkeletonDefinition,
    frame_path: str | Path | None,
    include_frame: bool,
    include_annotations: bool,
    show_labels: bool,
    point_radius: float,
    line_width: float = 2.0,
) -> QImage:
    """Render a frame preview with or without the underlying image."""

    width = max(1, annotation.width)
    height = max(1, annotation.height)
    if include_frame and frame_path:
        base_image = QImage(str(frame_path))
        if base_image.isNull():
            image = QImage(width, height, QImage.Format.Format_ARGB32)
            image.fill(QColor("#111318"))
        else:
            image = base_image.convertToFormat(QImage.Format.Format_ARGB32)
    else:
        image = QImage(width, height, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent if not include_frame else QColor("#111318"))

    if not include_annotations:
        return image

    effective_point_radius = _effective_point_radius(width, height, point_radius)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    font = QFont()
    font.setPointSize(10)
    painter.setFont(font)

    for start, end in skeleton.connections:
        if start >= len(annotation.keypoints) or end >= len(annotation.keypoints):
            continue
        start_state = annotation.keypoints[start]
        end_state = annotation.keypoints[end]
        if start_state.v == 0 or end_state.v == 0:
            continue
        painter.setPen(QPen(QColor("#7bdff2"), line_width))
        painter.drawLine(
            QPointF(start_state.x, start_state.y),
            QPointF(end_state.x, end_state.y),
        )

    for (shoulder_inner, shoulder_outer), hip_index in skeleton.bridge_connections:
        if max(shoulder_inner, shoulder_outer, hip_index) >= len(annotation.keypoints):
            continue
        inner_state = annotation.keypoints[shoulder_inner]
        outer_state = annotation.keypoints[shoulder_outer]
        hip_state = annotation.keypoints[hip_index]
        if inner_state.v == 0 or outer_state.v == 0 or hip_state.v == 0:
            continue
        painter.setPen(QPen(QColor("#7bdff2"), line_width))
        shoulder_mid = QPointF(
            (inner_state.x + outer_state.x) / 2,
            (inner_state.y + outer_state.y) / 2,
        )
        painter.drawLine(shoulder_mid, QPointF(hip_state.x, hip_state.y))

    for name, state in zip(skeleton.keypoints, annotation.keypoints):
        if state.v == 0:
            continue
        painter.setPen(QPen(QColor("#ffffff"), 2.2))
        painter.setBrush(_keypoint_color(state.v))
        painter.drawEllipse(
            QRectF(
                state.x - effective_point_radius,
                state.y - effective_point_radius,
                effective_point_radius * 2,
                effective_point_radius * 2,
            )
        )
        if state.contact:
            inner_radius = max(2.0, effective_point_radius * 0.55)
            painter.setPen(QPen(QColor("#00f5a0"), 2.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(
                QRectF(
                    state.x - inner_radius,
                    state.y - inner_radius,
                    inner_radius * 2,
                    inner_radius * 2,
                )
            )
        if show_labels:
            painter.setPen(QColor("#f2f2f2"))
            painter.drawText(
                QPointF(state.x + effective_point_radius + 4, state.y - effective_point_radius - 2),
                name,
            )

    painter.end()
    return image


def export_visual_sequence(
    project: ProjectData,
    skeleton: SkeletonDefinition,
    video_manager: VideoManager,
    output_dir: str | Path,
    start_frame: int,
    end_frame: int,
    export_kind: str,
    content_mode: str,
    show_labels: bool,
    point_radius: float,
    fps: float,
    line_width: float = 2.0,
) -> Path:
    """Export a preview sequence as PNG frames or MP4 video."""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    frame_indices = range(start_frame, end_frame + 1)
    include_frame = content_mode == "frame_and_annotations"
    include_annotations = True

    if export_kind == "frames":
        frames_dir = output_root / "rendered_frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        for frame_index in frame_indices:
            annotation = project.get_annotation(frame_index) or FrameAnnotation.empty(
                frame_index=frame_index,
                timestamp=video_manager.timestamp_for_frame(frame_index),
                width=video_manager.metadata.width,
                height=video_manager.metadata.height,
                num_keypoints=skeleton.size,
                contact_indices=skeleton.contact_indices,
            )
            frame_path = video_manager.get_frame_path(frame_index) if include_frame else None
            image = render_annotation_image(
                annotation=annotation,
                skeleton=skeleton,
                frame_path=frame_path,
                include_frame=include_frame,
                include_annotations=include_annotations,
                show_labels=show_labels,
                point_radius=point_radius,
                line_width=line_width,
            )
            image.save(str(frames_dir / f"render_{frame_index:06d}.png"))
        return frames_dir

    with tempfile.TemporaryDirectory(prefix="pose_preview_") as temp_dir:
        temp_path = Path(temp_dir)
        for export_index, frame_index in enumerate(frame_indices, start=1):
            annotation = project.get_annotation(frame_index) or FrameAnnotation.empty(
                frame_index=frame_index,
                timestamp=video_manager.timestamp_for_frame(frame_index),
                width=video_manager.metadata.width,
                height=video_manager.metadata.height,
                num_keypoints=skeleton.size,
                contact_indices=skeleton.contact_indices,
            )
            frame_path = video_manager.get_frame_path(frame_index) if include_frame else None
            image = render_annotation_image(
                annotation=annotation,
                skeleton=skeleton,
                frame_path=frame_path,
                include_frame=include_frame,
                include_annotations=include_annotations,
                show_labels=show_labels,
                point_radius=point_radius,
                line_width=line_width,
            )
            image.save(str(temp_path / f"render_{export_index:06d}.png"))
        return encode_image_sequence_to_video(
            temp_path / "render_%06d.png",
            output_root / "annotation_preview.mp4",
            fps=max(1.0, fps),
        )
