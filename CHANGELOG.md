# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1] - 2026-03-18

### Added
- Multi-item project structure with support for multiple videos and images in a single project.
- Item list panel for switching between imported media inside the same annotation session.
- Project merge workflow for importing legacy and newer projects into the active project.
- Help menu with an About dialog showing author and social handle.

### Changed
- Application title updated to `WS3D Pose Annotator v1.1`.
- Version source moved to the root `VERSION` file.
- COCO and simple JSON exports now consolidate all project items into one dataset-oriented output.
- Repository landing page documentation expanded to reflect the multi-item workflow.

## [1.0.0] - 2026-03-18

### Added
- Initial desktop release of `WS3D Pose Annotator`.
- Video and single-image annotation workflow built with `PySide6`.
- FFmpeg/ffprobe integration for media probing, frame extraction, and rendered exports.
- Interactive pose canvas with drag-and-drop keypoints, zoom, pan, labels, and skeleton lines.
- Configurable `POSE23` preset with foot contact metadata and COCO-style export support.
- Project persistence with autosave, recent projects, and resumable annotation sessions.
- Timeline markers for annotated frames and direct navigation to annotated frames.
- Export options for COCO JSON, simple JSON, rendered image sequences, preview videos, and current-frame snapshots.
- Undo/redo history for keypoint editing actions.

### Changed
- Application branding updated to `WS3D Pose Annotator`.
- Versioning moved to the root `VERSION` file for easier release management.
- Repository landing page documentation expanded in `README.md`.
