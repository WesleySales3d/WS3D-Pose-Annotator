"""Annotation data structures."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class KeypointState:
    """Single keypoint state."""

    x: float = 0.0
    y: float = 0.0
    v: int = 0
    contact: bool | None = None

    def is_marked(self) -> bool:
        return self.v > 0

    def clone(self) -> "KeypointState":
        return KeypointState(self.x, self.y, self.v, self.contact)

    def to_triplet(self) -> list[float | int]:
        return [round(self.x, 3), round(self.y, 3), int(self.v)]

    def to_record(self) -> list[float | int] | dict[str, float | int | bool | None]:
        if self.contact is None:
            return self.to_triplet()
        return {
            "x": round(self.x, 3),
            "y": round(self.y, 3),
            "v": int(self.v),
            "contact": int(bool(self.contact)),
        }

    @classmethod
    def from_record(cls, values: list[float | int] | dict[str, float | int | bool | None]) -> "KeypointState":
        if isinstance(values, dict):
            return cls(
                x=float(values.get("x", 0.0)),
                y=float(values.get("y", 0.0)),
                v=int(values.get("v", 0)),
                contact=bool(values.get("contact")) if values.get("contact") is not None else None,
            )
        if len(values) != 3:
            raise ValueError("Keypoint triplet must contain [x, y, v].")
        return cls(float(values[0]), float(values[1]), int(values[2]))


@dataclass
class FrameAnnotation:
    """Annotation for a single frame."""

    frame_index: int
    timestamp: float
    width: int
    height: int
    keypoints: list[KeypointState] = field(default_factory=list)

    def clone(self) -> "FrameAnnotation":
        return FrameAnnotation(
            frame_index=self.frame_index,
            timestamp=self.timestamp,
            width=self.width,
            height=self.height,
            keypoints=[keypoint.clone() for keypoint in self.keypoints],
        )

    @classmethod
    def empty(
        cls,
        frame_index: int,
        timestamp: float,
        width: int,
        height: int,
        num_keypoints: int,
        contact_indices: set[int] | None = None,
    ) -> "FrameAnnotation":
        contact_indices = contact_indices or set()
        return cls(
            frame_index=frame_index,
            timestamp=timestamp,
            width=width,
            height=height,
            keypoints=[
                KeypointState(contact=False if index in contact_indices else None)
                for index in range(num_keypoints)
            ],
        )

    @classmethod
    def from_dict(cls, data: dict) -> "FrameAnnotation":
        return cls(
            frame_index=int(data["frame_index"]),
            timestamp=float(data["timestamp"]),
            width=int(data["width"]),
            height=int(data["height"]),
            keypoints=[KeypointState.from_record(values) for values in data["keypoints"]],
        )

    def to_dict(self) -> dict:
        return {
            "frame_index": self.frame_index,
            "timestamp": self.timestamp,
            "width": self.width,
            "height": self.height,
            "keypoints": [keypoint.to_record() for keypoint in self.keypoints],
            "bbox": self.bbox(),
            "area": self.area(),
            "num_keypoints": self.num_keypoints(),
        }

    def has_any_marked_keypoint(self) -> bool:
        return any(keypoint.is_marked() for keypoint in self.keypoints)

    def num_keypoints(self) -> int:
        return sum(1 for keypoint in self.keypoints if keypoint.is_marked())

    def bbox(self) -> list[float]:
        valid = [(keypoint.x, keypoint.y) for keypoint in self.keypoints if keypoint.is_marked()]
        if not valid:
            return [0.0, 0.0, 0.0, 0.0]
        xs = [point[0] for point in valid]
        ys = [point[1] for point in valid]
        min_x = min(xs)
        max_x = max(xs)
        min_y = min(ys)
        max_y = max(ys)
        return [
            round(min_x, 3),
            round(min_y, 3),
            round(max_x - min_x, 3),
            round(max_y - min_y, 3),
        ]

    def area(self) -> float:
        _, _, width, height = self.bbox()
        return round(width * height, 3)

    def coco_keypoints(self) -> list[float | int]:
        values: list[float | int] = []
        for keypoint in self.keypoints:
            values.extend(keypoint.to_triplet())
        return values
