"""Skeleton preset definitions."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SkeletonDefinition:
    """Describes a pose skeleton."""

    name: str
    keypoints: list[str]
    connections: list[tuple[int, int]]
    bridge_connections: list[tuple[tuple[int, int], int]] = field(default_factory=list)
    bridge_mid_connections: list[tuple[int, tuple[int, int], int]] = field(default_factory=list)
    contact_keypoints: set[str] = field(default_factory=set)

    @property
    def size(self) -> int:
        return len(self.keypoints)

    @property
    def contact_indices(self) -> set[int]:
        return {
            index
            for index, keypoint_name in enumerate(self.keypoints)
            if keypoint_name in self.contact_keypoints
        }


POSE23 = SkeletonDefinition(
    name="POSE23",
    keypoints=[
        "nose",
        "left_eye",
        "right_eye",
        "left_ear",
        "right_ear",
        "center_shoulder",
        "left_shoulder_outer",
        "right_shoulder_outer",
        "left_elbow",
        "right_elbow",
        "left_wrist",
        "right_wrist",
        "spine_center",
        "left_hip",
        "right_hip",
        "left_knee",
        "right_knee",
        "left_ankle",
        "right_ankle",
        "left_heel",
        "right_heel",
        "left_toe_center",
        "right_toe_center",
    ],
    connections=[
        (0, 1),
        (0, 2),
        (1, 3),
        (2, 4),
        (5, 6),
        (5, 7),
        (6, 8),
        (8, 10),
        (7, 9),
        (9, 11),
        (13, 14),
        (13, 15),
        (15, 17),
        (14, 16),
        (16, 18),
        (17, 19),
        (17, 21),
        (19, 21),
        (18, 20),
        (18, 22),
        (20, 22),
    ],
    bridge_connections=[
        ((5, 6), 13),
        ((5, 7), 14),
    ],
    bridge_mid_connections=[
        (12, (5, 6), 13),
        (12, (5, 7), 14),
    ],
    contact_keypoints={"left_heel", "right_heel", "left_toe_center", "right_toe_center"},
)


COCO17 = SkeletonDefinition(
    name="COCO17",
    keypoints=[
        "nose",
        "left_eye",
        "right_eye",
        "left_ear",
        "right_ear",
        "left_shoulder",
        "right_shoulder",
        "left_elbow",
        "right_elbow",
        "left_wrist",
        "right_wrist",
        "left_hip",
        "right_hip",
        "left_knee",
        "right_knee",
        "left_ankle",
        "right_ankle",
    ],
    connections=[
        (0, 1),
        (0, 2),
        (1, 3),
        (2, 4),
        (5, 6),
        (5, 7),
        (7, 9),
        (6, 8),
        (8, 10),
        (5, 11),
        (6, 12),
        (11, 12),
        (11, 13),
        (13, 15),
        (12, 14),
        (14, 16),
    ],
)

_PRESETS = {
    POSE23.name: POSE23,
    COCO17.name: COCO17,
}


def get_skeleton(name: str) -> SkeletonDefinition:
    """Return a skeleton preset by name."""

    try:
        return _PRESETS[name]
    except KeyError as exc:
        raise ValueError(f"Unknown skeleton preset: {name}") from exc


def list_skeleton_names() -> list[str]:
    """Return the names of all embedded presets."""

    return sorted(_PRESETS)
