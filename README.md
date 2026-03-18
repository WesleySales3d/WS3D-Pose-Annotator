# WS3D Pose Annotator

Desktop app for manual 2D human pose annotation on videos and images, built with `Python 3.11+` and `PySide6`, with `FFmpeg/ffprobe` used for media probing, frame extraction, and rendered exports.

Current release: `v1.1`  
Version source: [VERSION](VERSION)  
Release notes: [CHANGELOG.md](CHANGELOG.md)

## Overview

`WS3D Pose Annotator` is a dataset-oriented annotation tool designed for projects that need more than a single clip per session.

With one project you can:

1. Import multiple videos and images.
2. Switch between them in an item list similar to a layer stack.
3. Annotate each item independently.
4. Save everything in one project file.
5. Merge older projects into the current project.
6. Export the whole project as one organized dataset.

## Highlights

- Desktop-native workflow with `PySide6`
- Multi-item projects with videos and still images together
- FFmpeg-backed frame extraction and export pipeline
- Drag-and-drop keypoint creation from the keypoint list
- Clickable timeline markers for annotated frames
- Previous/next annotated-frame navigation
- Undo and redo for keypoint edits
- Project autosave, recent projects, and project merge
- COCO-style export plus custom simple JSON export
- Rendered image/video export with annotations

## Main Features

### Project item workflow

- Import multiple videos and images into the same project
- Switch active media in the project item list
- Preserve annotations separately for each imported item
- Merge older projects into the current project with `Arquivo > Mesclar Projeto`

### Annotation canvas

- Central canvas based on `QGraphicsView`
- Draggable keypoints with live updates
- Skeleton rendering with configurable point size and line width
- Zoom with mouse wheel
- Pan with `Space + drag` or middle mouse drag
- Middle-button double click to reframe the media
- Overlay buttons to show/hide frame, show/hide annotations, and save the current frame image

### Timeline and navigation

- Frame slider with clickable annotated markers
- Previous/next frame
- Jump `-10` and `+10` frames
- Previous/next annotated frame
- Play/pause toggle and stop

### Keypoint management

- POSE23 preset included
- Left/right grouping by body category in the keypoint list
- Visibility states:
  - `0`: absent
  - `1`: occluded
  - `2`: visible
- Contact state for heel and toe-center keypoints
- Row color feedback in the keypoint table

### Persistence and export

- Save and reopen multi-item annotation projects
- Autosave support
- Recent projects submenu
- About dialog in `Ajuda > Sobre`
- Export to:
  - COCO-style keypoints JSON for the whole project
  - Simple JSON for the whole project
  - Rendered PNG sequence
  - Rendered MP4 preview
  - Current frame image snapshot

## Requirements

- Python `3.11+`
- `ffmpeg` and `ffprobe` available in `PATH`
- Windows, Linux, or macOS with graphical desktop support

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## FFmpeg Setup

1. Install FFmpeg with both `ffmpeg` and `ffprobe`.
2. Ensure the binaries are available in your system `PATH`.
3. Verify:

```bash
ffmpeg -version
ffprobe -version
```

## Run

```bash
python main.py
```

## Default Workflow

1. Create a new project or open an existing one.
2. Import media with `Arquivo > Abrir Vídeo` and `Arquivo > Abrir Imagem`.
3. Use the project item list to switch between imported videos and images.
4. Move through frames using the bottom controls or keyboard shortcuts.
5. Select a keypoint in the side panel.
6. Double click on the canvas or drag from the keypoint list into the frame.
7. Adjust visibility and contact state when needed.
8. Save the project or use `Arquivo > Mesclar Projeto` to bring in another project.
9. Export the dataset in the desired format.

## Keyboard Shortcuts

- `Left`: previous frame
- `Right`: next frame
- `Shift+Left`: back 10 frames
- `Shift+Right`: forward 10 frames
- `Up`: next annotated frame
- `Down`: previous annotated frame
- `Shift+Up`: last frame
- `Shift+Down`: first frame
- `Ctrl+Z`: undo
- `Ctrl+Shift+Z`: redo
- `Space`: play/pause

Canvas shortcuts:

- Mouse wheel: zoom
- `Space + drag`: pan
- Middle mouse drag: pan
- Middle mouse double click: fit media to view

## Project Format

Project files use:

- extension: `*.poseproj.json`
- multiple imported media items in the same project
- one annotation timeline per imported item
- active skeleton preset
- item-specific annotations and visited frames
- basic UI state
- cache directory reference per item

## Export Outputs

### COCO-style export

Generates:

- `images/*.png`
- `annotations/instances_keypoints.json`

The export traverses every imported item in the project and writes one consolidated dataset output.

### Simple JSON export

Readable multi-item annotation export for debugging and custom pipelines.

### Rendered preview export

- PNG sequence with overlay
- MP4 preview with overlay
- annotations-only rendering mode

## About

Menu:

- `Ajuda > Sobre`

Author:

- Wesley Sales
- Social: `@wesleysales3d`

## Repository Structure

```text
E:\MONOCAP\src
|-- main.py
|-- VERSION
|-- CHANGELOG.md
|-- README.md
|-- requirements.txt
`-- app
    |-- annotated_slider.py
    |-- annotation_model.py
    |-- canvas_view.py
    |-- export_coco.py
    |-- export_simple_json.py
    |-- export_visuals.py
    |-- ffmpeg_utils.py
    |-- history.py
    |-- keypoint_item.py
    |-- keypoint_table.py
    |-- main_window.py
    |-- project_model.py
    |-- settings.py
    |-- skeletons.py
    |-- video_manager.py
    `-- icons/
```

## Release Management

- App version is stored in [VERSION](VERSION)
- Release history is maintained in [CHANGELOG.md](CHANGELOG.md)
- UI title is generated from the version file automatically
