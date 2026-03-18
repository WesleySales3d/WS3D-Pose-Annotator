"""History models for undo/redo."""

from __future__ import annotations

from dataclasses import dataclass

from .annotation_model import FrameAnnotation


@dataclass
class HistoryEntry:
    """Stores a reversible change over the annotation set."""

    description: str
    before_annotations: dict[int, FrameAnnotation]
    before_frame_index: int
    after_annotations: dict[int, FrameAnnotation]
    after_frame_index: int
