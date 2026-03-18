"""Simple JSON export helpers."""

from __future__ import annotations

import json
from pathlib import Path

from .project_model import ProjectData
from .skeletons import SkeletonDefinition


def export_simple_json(project: ProjectData, skeleton: SkeletonDefinition, output_path: str | Path) -> Path:
    """Export a readable multi-item project dataset."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    items_payload = []

    for item in project.items:
        frames = []
        for frame_index in sorted(item.annotations):
            annotation = item.annotations[frame_index]
            keypoints = {}
            for name, state in zip(skeleton.keypoints, annotation.keypoints):
                if state.v > 0:
                    payload = {
                        "x": round(state.x, 3),
                        "y": round(state.y, 3),
                        "v": state.v,
                    }
                    if state.contact is not None:
                        payload["contact"] = int(bool(state.contact))
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
        items_payload.append(
            {
                "item_id": item.item_id,
                "name": item.name,
                "media_kind": item.media_kind,
                "media_path": item.media_path,
                "width": item.media_metadata.width,
                "height": item.media_metadata.height,
                "fps": item.media_metadata.fps,
                "total_frames": item.media_metadata.total_frames,
                "frames": frames,
            }
        )

    payload = {
        "project_version": project.version,
        "skeleton": skeleton.name,
        "items": items_payload,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
