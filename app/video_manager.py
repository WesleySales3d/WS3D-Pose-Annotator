"""Video metadata access and frame caching."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImageReader, QTransform

from .ffmpeg_utils import FFmpegError, extract_frame, probe_video
from .project_model import VideoMetadata

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


def _is_image_path(path: str | Path) -> bool:
    return Path(path).suffix.lower() in IMAGE_EXTENSIONS


def probe_image(image_path: str | Path) -> VideoMetadata:
    """Read basic metadata from a still image."""

    resolved = str(Path(image_path).resolve())
    reader = QImageReader(resolved)
    size = reader.size()
    if not size.isValid():
        raise FFmpegError("Não foi possível ler a imagem selecionada.")
    return VideoMetadata(
        video_path=resolved,
        width=size.width(),
        height=size.height(),
        fps=1.0,
        duration=0.0,
        total_frames=1,
    )


class VideoManager:
    """Manages metadata and cached frame extraction."""

    def __init__(self, video_path: str, metadata: VideoMetadata | None = None, cache_dir: str | None = None):
        self.video_path = str(Path(video_path).resolve())
        self.is_still_image = _is_image_path(self.video_path)
        self.metadata = metadata or (probe_image(self.video_path) if self.is_still_image else probe_video(self.video_path))
        self._owns_cache_dir = cache_dir is None
        self.cache_dir = Path(cache_dir) if cache_dir else Path(
            tempfile.mkdtemp(prefix="pose_video_annotator_")
        )
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_video_path(cls, video_path: str) -> "VideoManager":
        return cls.from_media_path(video_path)

    @classmethod
    def from_media_path(cls, media_path: str) -> "VideoManager":
        return cls(video_path=media_path)

    def timestamp_for_frame(self, frame_index: int) -> float:
        if self.metadata.fps <= 0:
            return 0.0
        return frame_index / self.metadata.fps

    def frame_cache_path(self, frame_index: int, image_format: str = "png") -> Path:
        return self.cache_dir / f"frame_{frame_index:06d}.{image_format}"

    def get_frame_path(self, frame_index: int, image_format: str = "png") -> Path:
        frame_index = max(0, min(frame_index, self.metadata.total_frames - 1))
        frame_path = self.frame_cache_path(frame_index, image_format=image_format)
        if not frame_path.exists():
            if self.is_still_image:
                self._render_image_to_cache(frame_path, image_format=image_format)
            else:
                extract_frame(self.video_path, frame_index, self.metadata.fps, frame_path, metadata=self.metadata)
        return frame_path

    def _render_image_to_cache(self, destination: Path, image_format: str = "png") -> None:
        image = QImageReader(self.video_path).read()
        if image.isNull():
            raise FFmpegError("Não foi possível carregar a imagem selecionada.")
        rotation = self.metadata.manual_rotation % 360
        if rotation:
            image = image.transformed(QTransform().rotate(rotation), Qt.TransformationMode.SmoothTransformation)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not image.save(str(destination), image_format.upper()):
            raise FFmpegError("Falha ao preparar a imagem para anotação.")

    def clear_cache(self) -> None:
        for child in self.cache_dir.glob('*'):
            if child.is_file():
                child.unlink(missing_ok=True)

    def prefetch_range(self, start_frame: int, end_frame: int, image_format: str = "png") -> None:
        """Reserved hook for future smarter prefetching."""

        del start_frame, end_frame, image_format

    def export_frame(self, frame_index: int, destination: str | Path, image_format: str = "png") -> Path:
        source = self.get_frame_path(frame_index, image_format=image_format)
        output = Path(destination)
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, output)
        return output

    def cleanup(self) -> None:
        if self._owns_cache_dir and self.cache_dir.exists():
            shutil.rmtree(self.cache_dir, ignore_errors=True)
