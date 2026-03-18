"""COCO keypoints export helpers."""

from __future__ import annotations

import json
from pathlib import Path

from .annotation_model import FrameAnnotation
from .project_model import ProjectData, ProjectItemData
from .skeletons import SkeletonDefinition
from .video_manager import VideoManager


def _frame_indices_for_item(item: ProjectItemData, mode: str) -> list[int]:
    if mode == "annotated":
        return [
            frame_index
            for frame_index, annotation in sorted(item.annotations.items())
            if annotation.num_keypoints() > 0
        ]
    return sorted(item.visited_frames)


def export_coco_dataset(
    project: ProjectData,
    skeleton: SkeletonDefinition,
    video_managers: dict[str, VideoManager],
    output_dir: str | Path,
    mode: str,
    json_name: str = "instances_keypoints.json",
    image_format: str = "png",
) -> Path:
    """Export all project items in COCO-style keypoints format."""

    base_dir = Path(output_dir)
    images_dir = base_dir / "images"
    annotations_dir = base_dir / "annotations"
    images_dir.mkdir(parents=True, exist_ok=True)
    annotations_dir.mkdir(parents=True, exist_ok=True)

    images = []
    annotations = []
    annotation_id = 1
    image_id = 1

    for item in project.items:
        manager = video_managers.get(item.item_id)
        if manager is None:
            continue
        frame_indices = _frame_indices_for_item(item, mode)
        for frame_index in frame_indices:
            annotation = item.get_annotation(frame_index)
            if annotation is None:
                metadata = manager.metadata
                annotation = FrameAnnotation.empty(
                    frame_index=frame_index,
                    timestamp=manager.timestamp_for_frame(frame_index),
                    width=metadata.width,
                    height=metadata.height,
                    num_keypoints=skeleton.size,
                    contact_indices=skeleton.contact_indices,
                )

            image_name = f"{item.item_id}_frame_{frame_index:06d}.{image_format}"
            image_path = images_dir / image_name
            manager.export_frame(frame_index, image_path, image_format=image_format)

            images.append(
                {
                    "id": image_id,
                    "file_name": f"images/{image_name}",
                    "width": annotation.width,
                    "height": annotation.height,
                    "source_item_id": item.item_id,
                    "source_item_name": item.name,
                    "source_media_path": item.media_path,
                    "frame_index": frame_index,
                }
            )
            annotations.append(
                {
                    "id": annotation_id,
                    "image_id": image_id,
                    "category_id": 1,
                    "bbox": annotation.bbox(),
                    "area": annotation.area(),
                    "iscrowd": 0,
                    "num_keypoints": annotation.num_keypoints(),
                    "keypoints": annotation.coco_keypoints(),
                    "contact_states": {
                        name: int(bool(state.contact))
                        for name, state in zip(skeleton.keypoints, annotation.keypoints)
                        if name in skeleton.contact_keypoints
                    },
                    "source_item_id": item.item_id,
                    "source_item_name": item.name,
                }
            )
            annotation_id += 1
            image_id += 1

    coco = {
        "images": images,
        "annotations": annotations,
        "categories": [
            {
                "id": 1,
                "name": "person",
                "supercategory": "person",
                "keypoints": skeleton.keypoints,
                "skeleton": [[start + 1, end + 1] for start, end in skeleton.connections],
                "contact_keypoints": sorted(skeleton.contact_keypoints),
            }
        ],
    }
    output_json = annotations_dir / json_name
    output_json.write_text(json.dumps(coco, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_json
