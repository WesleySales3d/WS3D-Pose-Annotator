"""COCO keypoints export helpers."""

from __future__ import annotations

import json
from pathlib import Path

from .annotation_model import FrameAnnotation
from .project_model import ProjectData
from .skeletons import SkeletonDefinition
from .video_manager import VideoManager


def export_coco_dataset(
    project: ProjectData,
    skeleton: SkeletonDefinition,
    video_manager: VideoManager,
    output_dir: str | Path,
    frame_indices: list[int],
    json_name: str = "instances_keypoints.json",
    image_format: str = "png",
) -> Path:
    """Export frames and annotations in COCO keypoints format."""

    base_dir = Path(output_dir)
    images_dir = base_dir / "images"
    annotations_dir = base_dir / "annotations"
    images_dir.mkdir(parents=True, exist_ok=True)
    annotations_dir.mkdir(parents=True, exist_ok=True)

    images = []
    annotations = []
    annotation_id = 1

    for image_id, frame_index in enumerate(sorted(frame_indices), start=1):
        annotation = project.get_annotation(frame_index)
        if annotation is None:
            metadata = video_manager.metadata
            annotation = FrameAnnotation.empty(
                frame_index=frame_index,
                timestamp=video_manager.timestamp_for_frame(frame_index),
                width=metadata.width,
                height=metadata.height,
                num_keypoints=skeleton.size,
            )

        image_name = f"frame_{frame_index:06d}.{image_format}"
        image_path = images_dir / image_name
        video_manager.export_frame(frame_index, image_path, image_format=image_format)

        images.append(
            {
                "id": image_id,
                "file_name": f"images/{image_name}",
                "width": annotation.width,
                "height": annotation.height,
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
            }
        )
        annotation_id += 1

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
