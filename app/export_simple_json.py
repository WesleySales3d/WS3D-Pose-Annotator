"""Simple JSON export helpers."""

from __future__ import annotations

import json
from pathlib import Path

from .project_model import ProjectData
from .skeletons import SkeletonDefinition


def export_simple_json(project: ProjectData, skeleton: SkeletonDefinition, output_path: str | Path) -> Path:
    """Export a readable project subset."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = []
    for frame_index in sorted(project.annotations):
        annotation = project.annotations[frame_index]
        keypoints = {}
        for name, state in zip(skeleton.keypoints, annotation.keypoints):
            if state.v > 0:
                payload = {
                    "x": round(state.x, 3),
                    "y": round(state.y, 3),
                    "v": state.v,
                }
                if state.contact is not None:
                    payload = {
                        "x": round(state.x, 3),
                        "y": round(state.y, 3),
                        "v": state.v,
                        "contact": int(bool(state.contact)),
                    }
                keypoints[name] = payload
        frames.append(
            {
                "frame_index": annotation.frame_index,
                "timestamp": annotation.timestamp,
                "width": annotation.width,
                "height": annotation.height,
                "keypoints": keypoints,
            }
        )
    payload = {
        "video_path": project.video_path,
        "skeleton": skeleton.name,
        "frames": frames,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
