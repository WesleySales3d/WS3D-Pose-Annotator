"""Main window for the pose annotation desktop app."""

from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import QSettings, QSignalBlocker, QTimer, Qt, QSize
from PySide6.QtGui import QAction, QBrush, QCloseEvent, QColor, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .annotated_slider import AnnotatedTimelineSlider
from .annotation_model import FrameAnnotation
from .canvas_view import AnnotationCanvas
from .export_coco import export_coco_dataset
from .export_simple_json import export_simple_json
from .export_visuals import export_visual_sequence, render_annotation_image
from .ffmpeg_utils import FFmpegError
from .history import HistoryEntry
from .keypoint_table import KeypointTable
from .project_model import ProjectData
from .settings import (
    APP_NAME,
    APP_TITLE,
    AUTOSAVE_INTERVAL_MS,
    DEFAULT_LINE_WIDTH,
    DEFAULT_POINT_RADIUS,
    MAX_RECENT_PROJECTS,
    PROJECT_EXTENSION,
    SUPPORTED_IMAGE_FILTER,
    SUPPORTED_MEDIA_FILTER,
    SUPPORTED_VIDEO_FILTER,
)
from .skeletons import POSE23, get_skeleton
from .video_manager import VideoManager

VISIBILITY_OPTIONS = [
    ("0 - Ausente", 0),
    ("1 - Ocluído", 1),
    ("2 - Visível", 2),
]


class NoWheelComboBox(QComboBox):
    """Ignores mouse-wheel changes unless the widget has focus."""

    def wheelEvent(self, event) -> None:
        if self.hasFocus():
            super().wheelEvent(event)
            return
        event.ignore()


class NoWheelSpinBox(QSpinBox):
    """Ignores mouse-wheel changes unless the widget has focus."""

    def wheelEvent(self, event) -> None:
        if self.hasFocus():
            super().wheelEvent(event)
            return
        event.ignore()


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    """Ignores mouse-wheel changes unless the widget has focus."""

    def wheelEvent(self, event) -> None:
        if self.hasFocus():
            super().wheelEvent(event)
            return
        event.ignore()


class ExportCocoDialog(QDialog):
    """Collect COCO export settings."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Exportar COCO")
        self.resize(420, 180)

        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("Selecione uma pasta de saída")
        browse_button = QPushButton("Escolher...")
        browse_button.clicked.connect(self._browse)

        output_row = QHBoxLayout()
        output_row.addWidget(self.output_edit, 1)
        output_row.addWidget(browse_button)

        self.frame_mode_combo = NoWheelComboBox()
        self.frame_mode_combo.addItem("Somente frames anotados", "annotated")
        self.frame_mode_combo.addItem("Todos os frames visitados", "visited")

        self.json_name_edit = QLineEdit("instances_keypoints.json")

        form = QFormLayout()
        form.addRow("Pasta de saída", self._wrap_layout(output_row))
        form.addRow("Frames", self.frame_mode_combo)
        form.addRow("Nome do JSON", self.json_name_edit)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel_button = QPushButton("Cancelar")
        cancel_button.clicked.connect(self.reject)
        export_button = QPushButton("Exportar")
        export_button.clicked.connect(self.accept)
        buttons.addWidget(cancel_button)
        buttons.addWidget(export_button)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addStretch(1)
        root.addLayout(buttons)

    def _wrap_layout(self, layout: QHBoxLayout) -> QWidget:
        widget = QWidget()
        widget.setLayout(layout)
        return widget

    def _browse(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Escolher pasta de saída")
        if directory:
            self.output_edit.setText(directory)

    def values(self) -> tuple[str, str, str]:
        return (
            self.output_edit.text().strip(),
            str(self.frame_mode_combo.currentData()),
            self.json_name_edit.text().strip() or "instances_keypoints.json",
        )


class ExportVisualDialog(QDialog):
    """Collect preview export settings."""

    def __init__(self, total_frames: int, default_fps: float, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Exportar Sequência/Vídeo")
        self.resize(460, 260)

        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("Selecione uma pasta de saída")
        browse_button = QPushButton("Escolher...")
        browse_button.clicked.connect(self._browse)

        output_row = QHBoxLayout()
        output_row.addWidget(self.output_edit, 1)
        output_row.addWidget(browse_button)

        self.start_spin = NoWheelSpinBox()
        self.start_spin.setRange(0, max(0, total_frames - 1))
        self.end_spin = NoWheelSpinBox()
        self.end_spin.setRange(0, max(0, total_frames - 1))
        self.end_spin.setValue(max(0, total_frames - 1))

        self.kind_combo = NoWheelComboBox()
        self.kind_combo.addItem("Sequência PNG", "frames")
        self.kind_combo.addItem("Vídeo MP4", "video")

        self.content_combo = NoWheelComboBox()
        self.content_combo.addItem("Frame + anotações", "frame_and_annotations")
        self.content_combo.addItem("Somente anotações", "annotations_only")

        self.fps_spin = NoWheelDoubleSpinBox()
        self.fps_spin.setRange(1.0, 240.0)
        self.fps_spin.setDecimals(3)
        self.fps_spin.setValue(default_fps if default_fps > 0 else 30.0)

        form = QFormLayout()
        form.addRow("Pasta de saída", self._wrap_layout(output_row))
        form.addRow("Frame inicial", self.start_spin)
        form.addRow("Frame final", self.end_spin)
        form.addRow("Saída", self.kind_combo)
        form.addRow("Conteúdo", self.content_combo)
        form.addRow("FPS", self.fps_spin)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel_button = QPushButton("Cancelar")
        cancel_button.clicked.connect(self.reject)
        export_button = QPushButton("Exportar")
        export_button.clicked.connect(self.accept)
        buttons.addWidget(cancel_button)
        buttons.addWidget(export_button)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addStretch(1)
        root.addLayout(buttons)

    def _wrap_layout(self, layout: QHBoxLayout) -> QWidget:
        widget = QWidget()
        widget.setLayout(layout)
        return widget

    def _browse(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Escolher pasta de saída")
        if directory:
            self.output_edit.setText(directory)

    def values(self) -> tuple[str, int, int, str, str, float]:
        return (
            self.output_edit.text().strip(),
            self.start_spin.value(),
            self.end_spin.value(),
            str(self.kind_combo.currentData()),
            str(self.content_combo.currentData()),
            self.fps_spin.value(),
        )


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1680, 980)

        self.project = ProjectData(skeleton_name=POSE23.name)
        self.video_manager: VideoManager | None = None
        self.current_project_path: str | None = None
        self.current_frame_index = 0
        self.current_annotation = FrameAnnotation.empty(
            0,
            0.0,
            1,
            1,
            POSE23.size,
            contact_indices=POSE23.contact_indices,
        )
        self.selected_keypoint_index = 0
        self._dirty = False
        self._loading_ui = False
        self._show_frame_layer = True
        self._show_annotation_layer = True
        self._row_to_keypoint_index: list[int] = []
        self._keypoint_index_to_row: dict[int, int] = {}
        self._undo_history: list[HistoryEntry] = []
        self._redo_history: list[HistoryEntry] = []
        self._pending_drag_history: tuple[dict[int, FrameAnnotation], int] | None = None
        self._recent_project_paths = self._load_recent_projects()

        self.play_timer = QTimer(self)
        self.play_timer.timeout.connect(self._advance_playback)

        self._build_ui()
        self._create_actions()
        self._create_shortcuts()
        self._create_autosave()
        self._apply_ui_state({})
        self._refresh_window_title()

    def _build_ui(self) -> None:
        self.canvas = AnnotationCanvas()
        self.canvas.set_skeleton(POSE23)
        self.canvas.keypoint_moved.connect(self._on_canvas_keypoint_moved)
        self.canvas.keypoint_selected.connect(self._set_current_keypoint)
        self.canvas.canvas_double_clicked.connect(self._on_canvas_double_clicked)
        self.canvas.keypoint_dropped.connect(self._on_canvas_keypoint_dropped)
        self.canvas.keypoint_drag_started.connect(self._on_keypoint_drag_started)
        self.canvas.keypoint_move_finished.connect(self._on_keypoint_move_finished)

        self.frame_toggle_button = self._make_canvas_toggle_button("frame.svg", "Mostrar/ocultar frame", True)
        self.frame_toggle_button.toggled.connect(self._on_frame_visibility_toggled)
        self.annotation_toggle_button = self._make_canvas_toggle_button(
            "annotations.svg",
            "Mostrar/ocultar anotações",
            True,
        )
        self.annotation_toggle_button.toggled.connect(self._on_annotation_visibility_toggled)
        self.export_frame_overlay_button = self._make_canvas_icon_button("camera.svg", "Salvar imagem do frame atual")
        self.export_frame_overlay_button.clicked.connect(self._export_current_frame_image)

        canvas_host = QWidget()
        canvas_grid = QGridLayout(canvas_host)
        canvas_grid.setContentsMargins(0, 0, 0, 0)
        canvas_grid.addWidget(self.canvas, 0, 0)
        overlay = QWidget()
        overlay_layout = QHBoxLayout(overlay)
        overlay_layout.setContentsMargins(12, 12, 12, 12)
        overlay_layout.addStretch(1)
        overlay_layout.addWidget(self.export_frame_overlay_button)
        overlay_layout.addWidget(self.frame_toggle_button)
        overlay_layout.addWidget(self.annotation_toggle_button)
        canvas_grid.addWidget(overlay, 0, 0, alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)

        self.keypoint_table = KeypointTable(0, 5)
        self.keypoint_table.setHorizontalHeaderLabels(["#", "Keypoint", "Status", "Vis", "Contato"])
        self.keypoint_table.setAlternatingRowColors(True)
        self.keypoint_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.keypoint_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.keypoint_table.verticalHeader().setVisible(False)
        self.keypoint_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.keypoint_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.keypoint_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.keypoint_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.keypoint_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.keypoint_table.itemSelectionChanged.connect(self._on_table_selection_changed)

        self.show_labels_checkbox = QCheckBox("Mostrar labels")
        self.show_labels_checkbox.setChecked(True)
        self.show_labels_checkbox.toggled.connect(self._on_show_labels_toggled)

        self.point_radius_spin = NoWheelSpinBox()
        self.point_radius_spin.setRange(4, 24)
        self.point_radius_spin.setValue(int(DEFAULT_POINT_RADIUS))
        self.point_radius_spin.valueChanged.connect(self._on_point_radius_changed)

        self.line_width_spin = NoWheelDoubleSpinBox()
        self.line_width_spin.setRange(0.5, 10.0)
        self.line_width_spin.setDecimals(1)
        self.line_width_spin.setSingleStep(0.5)
        self.line_width_spin.setValue(DEFAULT_LINE_WIDTH)
        self.line_width_spin.valueChanged.connect(self._on_line_width_changed)

        self.center_button = self._make_action_tile("center.svg", "Centralizar")
        self.center_button.clicked.connect(self._center_selected_keypoint)
        self.clear_keypoint_button = self._make_action_tile("clear_point.svg", "Limpar\nponto")
        self.clear_keypoint_button.clicked.connect(self._clear_selected_keypoint)
        self.mark_visible_button = self._make_action_tile("visible_all.svg", "Todos\nv=2")
        self.mark_visible_button.clicked.connect(self._mark_all_visible)
        self.clear_frame_button = self._make_action_tile("clear_frame.svg", "Limpar\nframe")
        self.clear_frame_button.clicked.connect(self._clear_current_frame)
        self.copy_prev_button = self._make_action_tile("copy_prev.svg", "Copiar\nprev")
        self.copy_prev_button.clicked.connect(lambda: self._copy_from_adjacent_frame(-1))
        self.copy_next_button = self._make_action_tile("copy_next.svg", "Copiar\nnext")
        self.copy_next_button.clicked.connect(lambda: self._copy_from_adjacent_frame(1))
        self.interpolate_button = self._make_action_tile("interpolate.svg", "Interpolar")
        self.interpolate_button.clicked.connect(self._interpolate_current_between_neighbors)
        self.undo_bulk_button = self._make_action_tile("undo.svg", "Desfazer")
        self.undo_bulk_button.clicked.connect(self._undo)
        self.undo_bulk_button.setEnabled(False)

        inspector_box = QGroupBox("Keypoints")
        inspector_layout = QVBoxLayout(inspector_box)
        inspector_layout.addWidget(self.keypoint_table, 1)
        inspector_hint = QLabel("Arraste um item da lista direto para o frame para criar o keypoint.")
        inspector_hint.setWordWrap(True)
        inspector_hint.setProperty("role", "muted")
        inspector_layout.addWidget(inspector_hint)

        display_box = QGroupBox("Exibição")
        display_layout = QFormLayout(display_box)
        display_layout.addRow(self.show_labels_checkbox)
        display_layout.addRow("Tamanho do ponto", self.point_radius_spin)
        display_layout.addRow("Espessura da linha", self.line_width_spin)

        actions_box = QGroupBox("Ações do frame")
        actions_layout = QGridLayout(actions_box)
        actions_layout.setContentsMargins(8, 8, 8, 8)
        actions_layout.setHorizontalSpacing(6)
        actions_layout.setVerticalSpacing(6)
        actions_layout.addWidget(self.center_button, 0, 0)
        actions_layout.addWidget(self.clear_keypoint_button, 0, 1)
        actions_layout.addWidget(self.mark_visible_button, 0, 2)
        actions_layout.addWidget(self.clear_frame_button, 0, 3)
        actions_layout.addWidget(self.copy_prev_button, 1, 0)
        actions_layout.addWidget(self.copy_next_button, 1, 1)
        actions_layout.addWidget(self.interpolate_button, 1, 2)
        actions_layout.addWidget(self.undo_bulk_button, 1, 3)

        lower_controls = QWidget()
        lower_controls_layout = QVBoxLayout(lower_controls)
        lower_controls_layout.setContentsMargins(0, 0, 0, 0)
        lower_controls_layout.addWidget(display_box)
        lower_controls_layout.addWidget(actions_box)
        lower_controls_layout.addStretch(1)

        side_panel = QSplitter(Qt.Orientation.Vertical)
        side_panel.addWidget(inspector_box)
        side_panel.addWidget(lower_controls)
        side_panel.setStretchFactor(0, 3)
        side_panel.setStretchFactor(1, 2)

        splitter = QSplitter()
        splitter.addWidget(canvas_host)
        splitter.addWidget(side_panel)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 2)

        self.slider = AnnotatedTimelineSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(0)
        self.slider.valueChanged.connect(self._on_slider_changed)
        self.slider.marker_clicked.connect(self._goto_frame)

        self.frame_info_label = QLabel("Frame 0 / 0")
        self.timestamp_label = QLabel("00:00:00.000")
        self.timestamp_label.setProperty("role", "muted")
        self.annotated_count_label = QLabel("Anotados: 0")
        self.annotated_count_label.setProperty("role", "muted")

        self.prev_annotated_button = self._make_nav_button("prev_annotated.svg", "Frame anotado anterior")
        self.prev_annotated_button.clicked.connect(lambda: self._goto_adjacent_annotated_frame(-1))
        self.play_button = self._make_nav_button("play.svg", "Reproduzir")
        self.play_button.clicked.connect(self._toggle_playback)
        self.stop_button = self._make_nav_button("stop.svg", "Parar")
        self.stop_button.clicked.connect(self._stop_video)
        self.jump_back_button = self._make_nav_button("back10.svg", "Voltar 10 frames")
        self.jump_back_button.clicked.connect(lambda: self._jump_frames(-10))
        self.prev_button = self._make_nav_button("prev_frame.svg", "Frame anterior")
        self.prev_button.clicked.connect(lambda: self._jump_frames(-1))
        self.next_button = self._make_nav_button("next_frame.svg", "Próximo frame")
        self.next_button.clicked.connect(lambda: self._jump_frames(1))
        self.jump_forward_button = self._make_nav_button("forward10.svg", "Avançar 10 frames")
        self.jump_forward_button.clicked.connect(lambda: self._jump_frames(10))
        self.next_annotated_button = self._make_nav_button("next_annotated.svg", "Próximo frame anotado")
        self.next_annotated_button.clicked.connect(lambda: self._goto_adjacent_annotated_frame(1))

        nav_layout = QHBoxLayout()
        nav_layout.setSpacing(6)
        nav_layout.addWidget(self.prev_annotated_button)
        nav_layout.addWidget(self.jump_back_button)
        nav_layout.addWidget(self.prev_button)
        nav_layout.addWidget(self.play_button)
        nav_layout.addWidget(self.stop_button)
        nav_layout.addWidget(self.next_button)
        nav_layout.addWidget(self.jump_forward_button)
        nav_layout.addWidget(self.next_annotated_button)
        nav_layout.addSpacing(12)
        nav_layout.addWidget(self.frame_info_label)
        nav_layout.addWidget(self.timestamp_label)
        nav_layout.addWidget(self.annotated_count_label)
        nav_layout.addStretch(1)

        bottom = QWidget()
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.addWidget(self.slider)
        bottom_layout.addLayout(nav_layout)

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.addWidget(splitter, 1)
        central_layout.addWidget(bottom)
        self.setCentralWidget(central)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Abra uma mídia para começar.")

        self._populate_keypoint_table()
        self._update_layer_buttons()
        self._update_play_button_state()
        self._update_annotation_navigation_buttons()

    def _create_actions(self) -> None:
        file_menu = self.menuBar().addMenu("&Arquivo")
        export_menu = self.menuBar().addMenu("&Exportar")
        edit_menu = self.menuBar().addMenu("&Editar")

        self.new_action = QAction("Novo Projeto", self)
        self.new_action.setShortcut(QKeySequence.StandardKey.New)
        self.new_action.triggered.connect(self.new_project)
        file_menu.addAction(self.new_action)

        self.open_project_action = QAction("Abrir Projeto", self)
        self.open_project_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_project_action.triggered.connect(self.open_project)
        file_menu.addAction(self.open_project_action)

        self.recent_projects_menu = file_menu.addMenu("Abrir Projetos Recentes")
        self._refresh_recent_projects_menu()

        self.save_project_action = QAction("Salvar Projeto", self)
        self.save_project_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_project_action.triggered.connect(self.save_project)
        file_menu.addAction(self.save_project_action)

        self.save_project_as_action = QAction("Salvar Projeto Como", self)
        self.save_project_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        self.save_project_as_action.triggered.connect(self.save_project_as)
        file_menu.addAction(self.save_project_as_action)

        file_menu.addSeparator()
        self.open_video_action = QAction("Abrir Vídeo", self)
        self.open_video_action.triggered.connect(self.open_video)
        file_menu.addAction(self.open_video_action)

        self.open_image_action = QAction("Abrir Imagem", self)
        self.open_image_action.triggered.connect(self.open_image)
        file_menu.addAction(self.open_image_action)

        file_menu.addSeparator()
        exit_action = QAction("Sair", self)
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        self.export_coco_action = QAction("Exportar COCO", self)
        self.export_coco_action.triggered.connect(self.export_coco)
        export_menu.addAction(self.export_coco_action)

        self.export_simple_action = QAction("Exportar JSON simples", self)
        self.export_simple_action.triggered.connect(self.export_simple_json_file)
        export_menu.addAction(self.export_simple_action)

        self.export_visual_action = QAction("Exportar Sequência/Vídeo", self)
        self.export_visual_action.triggered.connect(self.export_visual_preview)
        export_menu.addAction(self.export_visual_action)

        self.undo_bulk_action = QAction("Desfazer última ação em lote", self)
        self.undo_bulk_action.setShortcut(QKeySequence("Ctrl+Z"))
        self.undo_bulk_action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        self.undo_bulk_action.triggered.connect(self._undo)
        edit_menu.addAction(self.undo_bulk_action)

        self.redo_action = QAction("Refazer", self)
        self.redo_action.setShortcut(QKeySequence("Ctrl+Shift+Z"))
        self.redo_action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        self.redo_action.triggered.connect(self._redo)
        self.redo_action.setEnabled(False)
        edit_menu.addAction(self.redo_action)

    def _create_shortcuts(self) -> None:
        self._shortcuts: list[QShortcut] = []
        self._register_shortcut("Left", lambda: self._jump_frames(-1))
        self._register_shortcut("Right", lambda: self._jump_frames(1))
        self._register_shortcut("Up", lambda: self._goto_adjacent_annotated_frame(1))
        self._register_shortcut("Down", lambda: self._goto_adjacent_annotated_frame(-1))
        self._register_shortcut("Shift+Left", lambda: self._jump_frames(-10))
        self._register_shortcut("Shift+Right", lambda: self._jump_frames(10))
        self._register_shortcut("Shift+Up", self._goto_last_frame)
        self._register_shortcut("Shift+Down", lambda: self._goto_frame(0))
        self._register_shortcut("Home", lambda: self._goto_frame(0))
        self._register_shortcut("End", self._goto_last_frame)
        self._register_shortcut("Space", self._toggle_playback)
        self._register_shortcut("Ctrl+Shift+Z", self._redo)

    def _register_shortcut(self, sequence: str, handler) -> None:
        shortcut = QShortcut(QKeySequence(sequence), self)
        shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        shortcut.activated.connect(handler)
        self._shortcuts.append(shortcut)

    def _create_autosave(self) -> None:
        self.autosave_timer = QTimer(self)
        self.autosave_timer.timeout.connect(self._autosave)
        self.autosave_timer.start(AUTOSAVE_INTERVAL_MS)

    def _settings(self) -> QSettings:
        return QSettings(APP_NAME, APP_NAME)

    def _load_recent_projects(self) -> list[str]:
        value = self._settings().value("recent_projects", [])
        if isinstance(value, str):
            paths = [value]
        elif isinstance(value, list):
            paths = [str(item) for item in value]
        else:
            paths = []
        unique_paths: list[str] = []
        for path in paths:
            resolved = str(Path(path).resolve())
            if resolved not in unique_paths:
                unique_paths.append(resolved)
        return unique_paths[:MAX_RECENT_PROJECTS]

    def _save_recent_projects(self) -> None:
        self._settings().setValue("recent_projects", self._recent_project_paths[:MAX_RECENT_PROJECTS])

    def _remember_recent_project(self, path: str) -> None:
        resolved = str(Path(path).resolve())
        self._recent_project_paths = [item for item in self._recent_project_paths if item != resolved]
        self._recent_project_paths.insert(0, resolved)
        self._recent_project_paths = self._recent_project_paths[:MAX_RECENT_PROJECTS]
        self._save_recent_projects()
        self._refresh_recent_projects_menu()

    def _refresh_recent_projects_menu(self) -> None:
        if not hasattr(self, "recent_projects_menu"):
            return
        self.recent_projects_menu.clear()
        valid_paths = [path for path in self._recent_project_paths if Path(path).exists()]
        if valid_paths != self._recent_project_paths:
            self._recent_project_paths = valid_paths
            self._save_recent_projects()
        if not self._recent_project_paths:
            placeholder = QAction("Nenhum projeto recente", self)
            placeholder.setEnabled(False)
            self.recent_projects_menu.addAction(placeholder)
            return
        for path in self._recent_project_paths:
            action = QAction(Path(path).name, self)
            action.setToolTip(path)
            action.triggered.connect(lambda _checked=False, recent_path=path: self._open_recent_project(recent_path))
            self.recent_projects_menu.addAction(action)

    def _open_recent_project(self, path: str) -> None:
        if not Path(path).exists():
            self._recent_project_paths = [item for item in self._recent_project_paths if item != path]
            self._save_recent_projects()
            self._refresh_recent_projects_menu()
            self._show_error("Projeto recente", "O projeto selecionado não existe mais.")
            return
        self._load_project_file(path)

    def _keypoint_display_order(self, skeleton) -> list[int]:
        preferred_names = [
            "nose",
            "left_eye",
            "right_eye",
            "left_ear",
            "right_ear",
            "left_shoulder_inner",
            "right_shoulder_inner",
            "left_shoulder_outer",
            "right_shoulder_outer",
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
            "left_heel",
            "right_heel",
            "left_toe_center",
            "right_toe_center",
        ]
        available = {name: index for index, name in enumerate(skeleton.keypoints)}
        ordered = [available[name] for name in preferred_names if name in available]
        remaining = [index for index in range(skeleton.size) if index not in ordered]
        return ordered + remaining

    def _keypoint_index_for_row(self, row: int) -> int:
        return self._row_to_keypoint_index[row]

    def _row_for_keypoint_index(self, keypoint_index: int) -> int:
        return self._keypoint_index_to_row[keypoint_index]

    def _row_color_for_visibility(self, visibility_value: int) -> QColor:
        if visibility_value == 2:
            return QColor(45, 105, 65, 85)
        if visibility_value == 1:
            return QColor(133, 108, 34, 85)
        return QColor(122, 52, 52, 70)

    def _apply_row_visual_state(self, row: int, visibility_value: int) -> None:
        color = self._row_color_for_visibility(visibility_value)
        brush = QBrush(color)
        for column in (0, 1, 2, 4):
            item = self.keypoint_table.item(row, column)
            if item is not None:
                item.setBackground(brush)
        combo = self.keypoint_table.cellWidget(row, 3)
        if combo is not None:
            combo.setStyleSheet(
                f"background-color: rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()});"
            )
        holder = self.keypoint_table.cellWidget(row, 4)
        if holder is not None:
            holder.setStyleSheet(
                f"background-color: rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()});"
            )

    def _icon(self, name: str) -> QIcon:
        return QIcon(str(Path(__file__).resolve().parent / "icons" / name))

    def _make_nav_button(self, icon_name: str, tooltip: str) -> QPushButton:
        button = QPushButton()
        button.setIcon(self._icon(icon_name))
        button.setIconSize(QSize(22, 22))
        button.setFixedSize(36, 36)
        button.setToolTip(tooltip)
        return button

    def _make_canvas_toggle_button(self, icon_name: str, tooltip: str, checked: bool) -> QPushButton:
        button = QPushButton()
        button.setCheckable(True)
        button.setChecked(checked)
        button.setIcon(self._icon(icon_name))
        button.setIconSize(QSize(20, 20))
        button.setFixedSize(34, 34)
        button.setToolTip(tooltip)
        return button

    def _make_canvas_icon_button(self, icon_name: str, tooltip: str) -> QPushButton:
        button = QPushButton()
        button.setIcon(self._icon(icon_name))
        button.setIconSize(QSize(20, 20))
        button.setFixedSize(34, 34)
        button.setToolTip(tooltip)
        return button

    def _make_action_tile(self, icon_name: str, text: str) -> QToolButton:
        button = QToolButton()
        button.setIcon(self._icon(icon_name))
        button.setIconSize(QSize(24, 24))
        button.setText(text)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        button.setFixedSize(84, 64)
        return button

    def _populate_keypoint_table(self) -> None:
        skeleton = self._current_skeleton()
        self._row_to_keypoint_index = self._keypoint_display_order(skeleton)
        self._keypoint_index_to_row = {
            keypoint_index: row for row, keypoint_index in enumerate(self._row_to_keypoint_index)
        }
        self.keypoint_table.set_keypoint_indices_for_rows(self._row_to_keypoint_index)
        self._loading_ui = True
        self.keypoint_table.setRowCount(skeleton.size)
        for row, keypoint_index in enumerate(self._row_to_keypoint_index):
            name = skeleton.keypoints[keypoint_index]
            index_item = QTableWidgetItem(str(keypoint_index + 1))
            index_item.setFlags(index_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            name_item = QTableWidgetItem(name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            status_item = QTableWidgetItem("Ausente")
            status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.keypoint_table.setItem(row, 0, index_item)
            self.keypoint_table.setItem(row, 1, name_item)
            self.keypoint_table.setItem(row, 2, status_item)

            combo = NoWheelComboBox()
            for label, value in VISIBILITY_OPTIONS:
                combo.addItem(label, value)
            combo.currentIndexChanged.connect(lambda _=0, row=row: self._on_visibility_combo_changed(row))
            self.keypoint_table.setCellWidget(row, 3, combo)

            if keypoint_index in skeleton.contact_indices:
                checkbox = QCheckBox()
                checkbox.toggled.connect(lambda checked=False, row=row: self._on_contact_toggled(row, checked))
                holder = QWidget()
                holder_layout = QHBoxLayout(holder)
                holder_layout.setContentsMargins(0, 0, 0, 0)
                holder_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                holder_layout.addWidget(checkbox)
                self.keypoint_table.setCellWidget(row, 4, holder)
            else:
                contact_item = QTableWidgetItem("-")
                contact_item.setFlags(contact_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.keypoint_table.setItem(row, 4, contact_item)
            self._apply_row_visual_state(row, 0)
        self._loading_ui = False
        self._set_current_keypoint(0)

    def _contact_checkbox(self, row: int) -> QCheckBox | None:
        holder = self.keypoint_table.cellWidget(row, 4)
        if holder is None:
            return None
        return holder.findChild(QCheckBox)

    def _apply_ui_state(self, ui_state: dict) -> None:
        labels_visible = bool(ui_state.get("show_labels", True))
        point_radius = int(ui_state.get("point_radius", DEFAULT_POINT_RADIUS))
        line_width = float(ui_state.get("line_width", DEFAULT_LINE_WIDTH))
        show_frame = bool(ui_state.get("show_frame_layer", True))
        show_annotations = bool(ui_state.get("show_annotation_layer", True))
        with QSignalBlocker(self.show_labels_checkbox):
            self.show_labels_checkbox.setChecked(labels_visible)
        with QSignalBlocker(self.point_radius_spin):
            self.point_radius_spin.setValue(point_radius)
        with QSignalBlocker(self.line_width_spin):
            self.line_width_spin.setValue(line_width)
        self._show_frame_layer = show_frame
        self._show_annotation_layer = show_annotations
        self.canvas.set_show_labels(labels_visible)
        self.canvas.set_point_radius(point_radius)
        self.canvas.set_line_width(line_width)
        self.canvas.set_layer_visibility(show_frame, show_annotations)
        self._update_layer_buttons()

    def _capture_ui_state(self) -> dict:
        return {
            "show_labels": self.show_labels_checkbox.isChecked(),
            "point_radius": self.point_radius_spin.value(),
            "line_width": self.line_width_spin.value(),
            "show_frame_layer": self._show_frame_layer,
            "show_annotation_layer": self._show_annotation_layer,
        }

    def _snapshot_history_state(self) -> tuple[dict[int, FrameAnnotation], int]:
        return (
            {frame_index: annotation.clone() for frame_index, annotation in self.project.annotations.items()},
            self.current_frame_index,
        )

    def _push_history(self, description: str, before_state: tuple[dict[int, FrameAnnotation], int]) -> None:
        before_annotations, before_frame_index = before_state
        after_annotations, after_frame_index = self._snapshot_history_state()
        if before_annotations == after_annotations and before_frame_index == after_frame_index:
            return
        self._undo_history.append(
            HistoryEntry(
                description=description,
                before_annotations=before_annotations,
                before_frame_index=before_frame_index,
                after_annotations=after_annotations,
                after_frame_index=after_frame_index,
            )
        )
        self._redo_history.clear()
        self._update_history_actions()

    def _restore_history_state(self, annotations: dict[int, FrameAnnotation], frame_index: int) -> None:
        self.project.annotations = {key: value.clone() for key, value in annotations.items()}
        self.current_annotation = self.project.get_annotation(frame_index) or self._make_empty_annotation(frame_index)
        self._load_frame(frame_index)
        self._set_dirty()
        self._update_timeline_markers()

    def _undo(self) -> None:
        if not self._undo_history:
            return
        entry = self._undo_history.pop()
        self._redo_history.append(entry)
        self._restore_history_state(entry.before_annotations, entry.before_frame_index)
        self.statusBar().showMessage(f"Desfeito: {entry.description}")
        self._update_history_actions()

    def _redo(self) -> None:
        if not self._redo_history:
            return
        entry = self._redo_history.pop()
        self._undo_history.append(entry)
        self._restore_history_state(entry.after_annotations, entry.after_frame_index)
        self.statusBar().showMessage(f"Refeito: {entry.description}")
        self._update_history_actions()

    def _update_history_actions(self) -> None:
        can_undo = bool(self._undo_history)
        can_redo = bool(self._redo_history)
        self.undo_bulk_button.setEnabled(can_undo)
        self.undo_bulk_action.setEnabled(can_undo)
        self.redo_action.setEnabled(can_redo)

    def _update_timeline_markers(self) -> None:
        self.slider.set_markers(sorted(self.project.annotations))
        self._update_annotation_navigation_buttons()

    def _set_dirty(self, dirty: bool = True) -> None:
        self._dirty = dirty
        self._refresh_window_title()

    def _refresh_window_title(self) -> None:
        suffix = "*" if self._dirty else ""
        project_name = Path(self.current_project_path).name if self.current_project_path else "sem_projeto"
        self.setWindowTitle(f"{APP_TITLE} - {project_name}{suffix}")

    def _current_skeleton(self):
        return get_skeleton(self.project.skeleton_name)

    def _current_metadata(self):
        if not self.project.video_metadata:
            raise RuntimeError("No video loaded.")
        return self.project.video_metadata

    def _make_empty_annotation(self, frame_index: int) -> FrameAnnotation:
        metadata = self._current_metadata()
        skeleton = self._current_skeleton()
        return FrameAnnotation.empty(
            frame_index=frame_index,
            timestamp=self.video_manager.timestamp_for_frame(frame_index) if self.video_manager else 0.0,
            width=metadata.width,
            height=metadata.height,
            num_keypoints=skeleton.size,
            contact_indices=skeleton.contact_indices,
        )

    def _load_frame(self, frame_index: int, fit: bool = False) -> None:
        if not self.video_manager:
            return
        metadata = self._current_metadata()
        bounded = max(0, min(frame_index, metadata.total_frames - 1))
        frame_path = self.video_manager.get_frame_path(bounded)
        self.current_frame_index = bounded
        self.project.visited_frames.add(bounded)
        self.current_annotation = self.project.get_annotation(bounded) or self._make_empty_annotation(bounded)
        self.canvas.set_frame_image(frame_path)
        self.canvas.set_annotation(self.current_annotation)
        self.canvas.set_layer_visibility(self._show_frame_layer, self._show_annotation_layer)
        self.video_manager.prefetch_range(bounded + 1, bounded + 8)
        if fit:
            self.canvas.fit_content()
        self._refresh_keypoint_table()
        self._update_slider_and_labels()
        self._update_timeline_markers()
        self._update_play_button_state()
        self.statusBar().showMessage(f"Frame {bounded} carregado.")

    def _update_slider_and_labels(self) -> None:
        metadata = self.project.video_metadata
        if not metadata:
            self.frame_info_label.setText("Frame 0 / 0")
            self.timestamp_label.setText("00:00:00.000")
            return
        with QSignalBlocker(self.slider):
            self.slider.setMaximum(max(0, metadata.total_frames - 1))
            self.slider.setValue(self.current_frame_index)
        self.frame_info_label.setText(f"Frame {self.current_frame_index + 1} / {metadata.total_frames}")
        self.timestamp_label.setText(self._format_timestamp(self.current_annotation.timestamp))
        self.annotated_count_label.setText(f"Anotados: {len(self.project.annotations)}")

    def _format_timestamp(self, seconds: float) -> str:
        milliseconds = int(round(seconds * 1000))
        hours = milliseconds // 3600000
        minutes = (milliseconds % 3600000) // 60000
        secs = (milliseconds % 60000) // 1000
        millis = milliseconds % 1000
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"

    def _refresh_keypoint_table(self) -> None:
        skeleton = self._current_skeleton()
        self._loading_ui = True
        for row, keypoint_index in enumerate(self._row_to_keypoint_index):
            keypoint = self.current_annotation.keypoints[keypoint_index]
            status_item = self.keypoint_table.item(row, 2)
            if keypoint.contact is None:
                status_item.setText(f"x={keypoint.x:.1f}, y={keypoint.y:.1f}, v={keypoint.v}")
            else:
                status_item.setText(
                    f"x={keypoint.x:.1f}, y={keypoint.y:.1f}, v={keypoint.v}, c={int(bool(keypoint.contact))}"
                )
            combo = self.keypoint_table.cellWidget(row, 3)
            if isinstance(combo, QComboBox):
                combo.setCurrentIndex(max(0, min(keypoint.v, combo.count() - 1)))
            checkbox = self._contact_checkbox(row)
            if checkbox:
                checkbox.setChecked(bool(keypoint.contact))
                checkbox.setEnabled(keypoint_index in skeleton.contact_indices)
            self._apply_row_visual_state(row, keypoint.v)
        self._loading_ui = False
        self._select_row(self.selected_keypoint_index)

    def _select_row(self, keypoint_index: int) -> None:
        self.selected_keypoint_index = keypoint_index
        self.canvas.set_active_keypoint(keypoint_index)
        row = self._keypoint_index_to_row.get(keypoint_index, -1)
        if 0 <= row < self.keypoint_table.rowCount():
            self.keypoint_table.selectRow(row)

    def _commit_current_annotation(self) -> None:
        if self.current_annotation.has_any_marked_keypoint():
            self.project.upsert_annotation(self.current_annotation)
        else:
            self.project.remove_annotation(self.current_annotation.frame_index)
        self.project.ui_state = self._capture_ui_state()
        self._update_timeline_markers()

    def _goto_frame(self, frame_index: int) -> None:
        if not self.video_manager:
            return
        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            self._load_frame(frame_index)
        except FFmpegError as exc:
            self._pause_video()
            self._show_error("Erro ao carregar frame", str(exc))
        finally:
            QApplication.restoreOverrideCursor()

    def _goto_last_frame(self) -> None:
        if not self.project.video_metadata:
            return
        self._goto_frame(self.project.video_metadata.total_frames - 1)

    def _jump_frames(self, delta: int) -> None:
        self._goto_frame(self.current_frame_index + delta)

    def _update_play_button_state(self) -> None:
        playing = self.play_timer.isActive()
        self.play_button.setIcon(self._icon("pause.svg" if playing else "play.svg"))
        self.play_button.setToolTip("Pausar" if playing else "Reproduzir")

    def _update_annotation_navigation_buttons(self) -> None:
        previous_exists = any(frame < self.current_frame_index for frame in self.project.annotations)
        next_exists = any(frame > self.current_frame_index for frame in self.project.annotations)
        self.prev_annotated_button.setEnabled(previous_exists)
        self.next_annotated_button.setEnabled(next_exists)

    def _goto_adjacent_annotated_frame(self, direction: int) -> None:
        annotated_frames = sorted(self.project.annotations)
        if direction < 0:
            candidates = [frame for frame in annotated_frames if frame < self.current_frame_index]
            if candidates:
                self._goto_frame(candidates[-1])
            return
        candidates = [frame for frame in annotated_frames if frame > self.current_frame_index]
        if candidates:
            self._goto_frame(candidates[0])

    def _toggle_playback(self) -> None:
        if self.play_timer.isActive():
            self._pause_video()
        else:
            self._play_video()

    def _play_video(self) -> None:
        if not self.project.video_metadata:
            return
        fps = self.project.video_metadata.fps or 30.0
        if self.video_manager:
            self.video_manager.prefetch_range(self.current_frame_index + 1, self.current_frame_index + 24)
        self.play_timer.start(max(1, round(1000 / fps)))
        self._update_play_button_state()
        self.statusBar().showMessage("Reproduzindo.")

    def _pause_video(self) -> None:
        self.play_timer.stop()
        self._update_play_button_state()
        self.statusBar().showMessage("Pausado.")

    def _stop_video(self) -> None:
        self.play_timer.stop()
        self._update_play_button_state()
        self._goto_frame(0)
        self.statusBar().showMessage("Parado.")

    def _advance_playback(self) -> None:
        if not self.project.video_metadata:
            self.play_timer.stop()
            return
        if self.current_frame_index >= self.project.video_metadata.total_frames - 1:
            self._pause_video()
            return
        self._goto_frame(self.current_frame_index + 1)

    def _on_slider_changed(self, value: int) -> None:
        if self._loading_ui:
            return
        self._goto_frame(value)

    def _set_current_keypoint(self, index: int) -> None:
        self._select_row(index)

    def _on_table_selection_changed(self) -> None:
        if self._loading_ui:
            return
        current_row = self.keypoint_table.currentRow()
        if current_row >= 0:
            self._select_row(self._keypoint_index_for_row(current_row))

    def _on_visibility_combo_changed(self, row: int) -> None:
        if self._loading_ui or row >= len(self.current_annotation.keypoints):
            return
        before_state = self._snapshot_history_state()
        combo = self.keypoint_table.cellWidget(row, 3)
        if not isinstance(combo, QComboBox):
            return
        visibility_value = int(combo.currentData())
        keypoint_index = self._keypoint_index_for_row(row)
        keypoint = self.current_annotation.keypoints[keypoint_index]
        keypoint.v = visibility_value
        if visibility_value > 0 and keypoint.x == 0 and keypoint.y == 0:
            metadata = self._current_metadata()
            keypoint.x = metadata.width / 2
            keypoint.y = metadata.height / 2
        if visibility_value == 0:
            keypoint.x = 0.0
            keypoint.y = 0.0
            if keypoint.contact is not None:
                keypoint.contact = False
        self.current_annotation.keypoints[keypoint_index] = keypoint
        self._commit_current_annotation()
        self.canvas.set_annotation(self.current_annotation)
        self._refresh_keypoint_table()
        self._set_dirty()
        self._push_history("Alterar visibilidade", before_state)

    def _on_contact_toggled(self, row: int, checked: bool) -> None:
        if self._loading_ui or row >= len(self.current_annotation.keypoints):
            return
        before_state = self._snapshot_history_state()
        keypoint_index = self._keypoint_index_for_row(row)
        keypoint = self.current_annotation.keypoints[keypoint_index]
        if keypoint.contact is None:
            return
        keypoint.contact = checked
        if checked and keypoint.v == 0:
            metadata = self._current_metadata()
            keypoint.v = 2
            keypoint.x = metadata.width / 2
            keypoint.y = metadata.height / 2
        self.current_annotation.keypoints[keypoint_index] = keypoint
        self._commit_current_annotation()
        self.canvas.set_annotation(self.current_annotation)
        self._refresh_keypoint_table()
        self._set_dirty()
        self._push_history("Alterar contato", before_state)

    def _apply_keypoint_position(self, index: int, x: float, y: float) -> None:
        keypoint = self.current_annotation.keypoints[index]
        keypoint.x = max(0.0, min(x, float(self.current_annotation.width)))
        keypoint.y = max(0.0, min(y, float(self.current_annotation.height)))
        if keypoint.v == 0:
            keypoint.v = 2
        self.current_annotation.keypoints[index] = keypoint
        self._commit_current_annotation()
        self.canvas.set_annotation(self.current_annotation)
        self._refresh_keypoint_table()
        self._set_dirty()

    def _on_canvas_keypoint_moved(self, index: int, x: float, y: float) -> None:
        self._apply_keypoint_position(index, x, y)

    def _on_keypoint_drag_started(self, index: int) -> None:
        del index
        self._pending_drag_history = self._snapshot_history_state()

    def _on_keypoint_move_finished(self, index: int, x: float, y: float) -> None:
        del index, x, y
        if self._pending_drag_history is None:
            return
        self._push_history("Mover keypoint", self._pending_drag_history)
        self._pending_drag_history = None

    def _on_canvas_double_clicked(self, x: float, y: float) -> None:
        before_state = self._snapshot_history_state()
        self._apply_keypoint_position(self.selected_keypoint_index, x, y)
        self._push_history("Posicionar keypoint", before_state)

    def _on_canvas_keypoint_dropped(self, index: int, x: float, y: float) -> None:
        before_state = self._snapshot_history_state()
        self._set_current_keypoint(index)
        self._apply_keypoint_position(index, x, y)
        self._push_history("Criar keypoint por arraste", before_state)
        self.statusBar().showMessage("Keypoint criado por arraste.")

    def _on_show_labels_toggled(self, checked: bool) -> None:
        self.canvas.set_show_labels(checked)
        self.project.ui_state = self._capture_ui_state()
        self._set_dirty()

    def _on_point_radius_changed(self, value: int) -> None:
        self.canvas.set_point_radius(float(value))
        self.project.ui_state = self._capture_ui_state()
        self._set_dirty()

    def _on_line_width_changed(self, value: float) -> None:
        self.canvas.set_line_width(float(value))
        self.project.ui_state = self._capture_ui_state()
        self._set_dirty()

    def _on_frame_visibility_toggled(self, checked: bool) -> None:
        self._show_frame_layer = checked
        self.canvas.set_layer_visibility(self._show_frame_layer, self._show_annotation_layer)
        self._update_layer_buttons()
        self._set_dirty()

    def _on_annotation_visibility_toggled(self, checked: bool) -> None:
        self._show_annotation_layer = checked
        self.canvas.set_layer_visibility(self._show_frame_layer, self._show_annotation_layer)
        self._update_layer_buttons()
        self._set_dirty()

    def _update_layer_buttons(self) -> None:
        self.frame_toggle_button.setIcon(self._icon("frame.svg" if self._show_frame_layer else "frame_off.svg"))
        self.annotation_toggle_button.setIcon(
            self._icon("annotations.svg" if self._show_annotation_layer else "annotations_off.svg")
        )
        with QSignalBlocker(self.frame_toggle_button):
            self.frame_toggle_button.setChecked(self._show_frame_layer)
        with QSignalBlocker(self.annotation_toggle_button):
            self.annotation_toggle_button.setChecked(self._show_annotation_layer)

    def _center_selected_keypoint(self) -> None:
        self.canvas.center_on_keypoint(self.selected_keypoint_index)

    def _clear_selected_keypoint(self) -> None:
        before_state = self._snapshot_history_state()
        keypoint = self.current_annotation.keypoints[self.selected_keypoint_index]
        keypoint.x = 0.0
        keypoint.y = 0.0
        keypoint.v = 0
        if keypoint.contact is not None:
            keypoint.contact = False
        self.current_annotation.keypoints[self.selected_keypoint_index] = keypoint
        self._commit_current_annotation()
        self.canvas.set_annotation(self.current_annotation)
        self._refresh_keypoint_table()
        self._set_dirty()
        self._push_history("Limpar keypoint", before_state)

    def _mark_all_visible(self) -> None:
        before_state = self._snapshot_history_state()
        metadata = self._current_metadata()
        for keypoint in self.current_annotation.keypoints:
            if keypoint.v == 0:
                keypoint.x = metadata.width / 2
                keypoint.y = metadata.height / 2
            keypoint.v = 2
        self._commit_current_annotation()
        self.canvas.set_annotation(self.current_annotation)
        self._refresh_keypoint_table()
        self._set_dirty()
        self._push_history("Marcar todos como visíveis", before_state)

    def _clear_current_frame(self) -> None:
        before_state = self._snapshot_history_state()
        self.current_annotation = self._make_empty_annotation(self.current_frame_index)
        self._commit_current_annotation()
        self.canvas.set_annotation(self.current_annotation)
        self._refresh_keypoint_table()
        self._set_dirty()
        self._push_history("Limpar frame", before_state)

    def _copy_from_adjacent_frame(self, direction: int) -> None:
        if not self.project.video_metadata:
            return
        before_state = self._snapshot_history_state()
        annotated_frames = sorted(self.project.annotations)
        if direction < 0:
            candidates = [frame for frame in annotated_frames if frame < self.current_frame_index]
            source_frame = candidates[-1] if candidates else None
        else:
            candidates = [frame for frame in annotated_frames if frame > self.current_frame_index]
            source_frame = candidates[0] if candidates else None
        if source_frame is None:
            self.statusBar().showMessage("Não há frame anotado compatível para copiar.")
            return
        source_annotation = self.project.get_annotation(source_frame)
        if not source_annotation:
            self.statusBar().showMessage("Não há anotação no frame selecionado para cópia.")
            return
        target = source_annotation.clone()
        target.frame_index = self.current_frame_index
        target.timestamp = self.video_manager.timestamp_for_frame(self.current_frame_index) if self.video_manager else 0.0
        self.current_annotation = target
        self._commit_current_annotation()
        self.canvas.set_annotation(self.current_annotation)
        self._refresh_keypoint_table()
        self._set_dirty()
        self._push_history("Copiar anotação adjacente", before_state)

    def _interpolate_current_between_neighbors(self) -> None:
        previous_candidates = [frame for frame in self.project.annotations if frame < self.current_frame_index]
        next_candidates = [frame for frame in self.project.annotations if frame > self.current_frame_index]
        if not previous_candidates or not next_candidates:
            self.statusBar().showMessage("É preciso ter um frame anotado anterior e outro posterior.")
            return

        start_frame = max(previous_candidates)
        end_frame = min(next_candidates)
        if end_frame <= start_frame:
            self.statusBar().showMessage("Não foi possível determinar os frames anotados vizinhos.")
            return

        start_annotation = self.project.get_annotation(start_frame)
        end_annotation = self.project.get_annotation(end_frame)
        if not start_annotation or not end_annotation:
            self.statusBar().showMessage("Os frames anotados vizinhos precisam existir.")
            return

        before_state = self._snapshot_history_state()
        total_steps = end_frame - start_frame
        ratio = (self.current_frame_index - start_frame) / total_steps
        annotation = self.project.get_annotation(self.current_frame_index) or self._make_empty_annotation(self.current_frame_index)
        for index, (start_point, end_point) in enumerate(zip(start_annotation.keypoints, end_annotation.keypoints)):
            interpolated = annotation.keypoints[index]
            if start_point.v == 0 or end_point.v == 0:
                continue
            interpolated.x = start_point.x + (end_point.x - start_point.x) * ratio
            interpolated.y = start_point.y + (end_point.y - start_point.y) * ratio
            interpolated.v = min(start_point.v, end_point.v)
            if interpolated.contact is not None:
                interpolated.contact = bool(start_point.contact or end_point.contact)
            annotation.keypoints[index] = interpolated

        self.current_annotation = annotation
        self._commit_current_annotation()
        self.canvas.set_annotation(self.current_annotation)
        self._refresh_keypoint_table()
        self._set_dirty()
        self._push_history("Interpolar frame atual", before_state)
        self.statusBar().showMessage(
            f"Interpolação aplicada usando os frames anotados {start_frame} e {end_frame}."
        )

    def _export_current_frame_image(self) -> None:
        if not self.video_manager or not self.project.video_metadata:
            self._show_error("Exportar frame atual", "Abra uma mídia antes de exportar o frame atual.")
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar frame atual como imagem",
            f"frame_{self.current_frame_index:06d}.png",
            "PNG (*.png);;JPEG (*.jpg *.jpeg)",
        )
        if not file_path:
            return
        frame_path = self.video_manager.get_frame_path(self.current_frame_index) if self._show_frame_layer else None
        image = render_annotation_image(
            annotation=self.current_annotation,
            skeleton=self._current_skeleton(),
            frame_path=frame_path,
            include_frame=self._show_frame_layer,
            include_annotations=self._show_annotation_layer,
            show_labels=self.show_labels_checkbox.isChecked(),
            point_radius=float(self.point_radius_spin.value()),
            line_width=float(self.line_width_spin.value()),
        )
        if not image.save(file_path):
            self._show_error("Exportar frame atual", "Não foi possível salvar a imagem do frame atual.")
            return
        self.statusBar().showMessage(f"Frame atual exportado em {file_path}")

    def _autosave_path(self) -> Path:
        if self.current_project_path:
            path = Path(self.current_project_path)
            return path.with_name(f"{path.stem}.autosave{path.suffix}")
        return Path(tempfile.gettempdir()) / f"pose_video_annotator_unsaved{PROJECT_EXTENSION}"

    def _autosave(self) -> None:
        if not self._dirty:
            return
        try:
            self.project.ui_state = self._capture_ui_state()
            self.project.cache_dir = str(self.video_manager.cache_dir) if self.video_manager else None
            self.project.save(self._autosave_path())
            self.statusBar().showMessage("Autosave atualizado.")
        except Exception as exc:
            self.statusBar().showMessage(f"Autosave falhou: {exc}")

    def _save_project_to(self, path: str) -> None:
        self.project.video_path = self.video_manager.video_path if self.video_manager else self.project.video_path
        self.project.cache_dir = str(self.video_manager.cache_dir) if self.video_manager else None
        self.project.ui_state = self._capture_ui_state()
        self.project.save(path)
        self.current_project_path = path
        self._remember_recent_project(path)
        self._set_dirty(False)
        self.statusBar().showMessage(f"Projeto salvo em {path}")

    def _confirm_discard_changes(self) -> bool:
        if not self._dirty:
            return True
        reply = QMessageBox.question(
            self,
            "Alterações não salvas",
            "Há alterações não salvas. Deseja salvar antes de continuar?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Cancel:
            return False
        if reply == QMessageBox.StandardButton.Yes:
            return self.save_project()
        return True

    def new_project(self) -> None:
        if not self._confirm_discard_changes():
            return
        self._pause_video()
        self._undo_history.clear()
        self._redo_history.clear()
        self._update_history_actions()
        if self.video_manager:
            self.video_manager.cleanup()
        self.project = ProjectData(skeleton_name=POSE23.name)
        self.video_manager = None
        self.current_project_path = None
        self.current_frame_index = 0
        self.current_annotation = FrameAnnotation.empty(
            0,
            0.0,
            1,
            1,
            POSE23.size,
            contact_indices=POSE23.contact_indices,
        )
        self.canvas.set_skeleton(POSE23)
        self.canvas.clear_image()
        self._populate_keypoint_table()
        self.canvas.set_annotation(self.current_annotation)
        self.slider.setMaximum(0)
        self.slider.setValue(0)
        self._update_timeline_markers()
        self.frame_info_label.setText("Frame 0 / 0")
        self.timestamp_label.setText("00:00:00.000")
        self.annotated_count_label.setText("Anotados: 0")
        self._update_play_button_state()
        self._update_annotation_navigation_buttons()
        self.statusBar().showMessage("Novo projeto criado. Abra um vídeo ou uma imagem para começar.")
        self._set_dirty(False)

    def _load_media_path(self, file_path: str, source_label: str) -> None:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self._pause_video()
            if self.video_manager:
                self.video_manager.cleanup()
            self.video_manager = VideoManager.from_media_path(file_path)
            self._undo_history.clear()
            self._redo_history.clear()
            self._update_history_actions()
            self.project = ProjectData(
                video_path=self.video_manager.video_path,
                video_metadata=self.video_manager.metadata,
                skeleton_name=POSE23.name,
            )
            self.current_project_path = None
            self.canvas.set_skeleton(self._current_skeleton())
            self._populate_keypoint_table()
            self._load_frame(0, fit=True)
            self._set_dirty(False)
            self.statusBar().showMessage(f"{source_label} carregad{ 'a' if source_label == 'Imagem' else 'o' } com sucesso.")
        except FFmpegError as exc:
            self._show_error(f"Erro ao abrir {source_label.lower()}", str(exc))
        finally:
            QApplication.restoreOverrideCursor()

    def open_video(self) -> None:
        if not self._confirm_discard_changes():
            return
        file_path, _ = QFileDialog.getOpenFileName(self, "Abrir vídeo", "", SUPPORTED_VIDEO_FILTER)
        if not file_path:
            return
        self._load_media_path(file_path, "Vídeo")

    def open_image(self) -> None:
        if not self._confirm_discard_changes():
            return
        file_path, _ = QFileDialog.getOpenFileName(self, "Abrir imagem", "", SUPPORTED_IMAGE_FILTER)
        if not file_path:
            return
        self._load_media_path(file_path, "Imagem")

    def save_project(self) -> bool:
        if not self.project.video_metadata:
            self._show_error("Salvar projeto", "Abra uma mídia antes de salvar o projeto.")
            return False
        if not self.current_project_path:
            return self.save_project_as()
        try:
            self._save_project_to(self.current_project_path)
            return True
        except Exception as exc:
            self._show_error("Erro ao salvar projeto", str(exc))
            return False

    def save_project_as(self) -> bool:
        if not self.project.video_metadata:
            self._show_error("Salvar projeto", "Abra uma mídia antes de salvar o projeto.")
            return False
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar projeto",
            "",
            f"Projetos (*{PROJECT_EXTENSION})",
        )
        if not file_path:
            return False
        if not file_path.endswith(PROJECT_EXTENSION):
            file_path = f"{file_path}{PROJECT_EXTENSION}"
        try:
            self._save_project_to(file_path)
            return True
        except Exception as exc:
            self._show_error("Erro ao salvar projeto", str(exc))
            return False
    def _load_project_file(self, file_path: str, *, confirm_discard: bool = True) -> None:
        if confirm_discard and not self._confirm_discard_changes():
            return
        if not file_path:
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            project = ProjectData.load(file_path)
            if not project.video_path or not Path(project.video_path).exists():
                resolved, _ = QFileDialog.getOpenFileName(
                    self,
                    "Localizar mídia do projeto",
                    "",
                    SUPPORTED_MEDIA_FILTER,
                )
                if not resolved:
                    return
                project.video_path = resolved
            self._pause_video()
            if self.video_manager:
                self.video_manager.cleanup()
            self.video_manager = VideoManager(
                video_path=project.video_path,
                metadata=project.video_metadata,
                cache_dir=project.cache_dir,
            )
            self.project = project
            self._undo_history.clear()
            self._redo_history.clear()
            self._update_history_actions()
            self.current_project_path = file_path
            self._remember_recent_project(file_path)
            self.canvas.set_skeleton(self._current_skeleton())
            self._populate_keypoint_table()
            self._apply_ui_state(self.project.ui_state)
            first_frame = min(self.project.annotations) if self.project.annotations else 0
            self._load_frame(first_frame, fit=True)
            self._set_dirty(False)
            self.statusBar().showMessage("Projeto reaberto com sucesso.")
        except Exception as exc:
            self._show_error("Erro ao abrir projeto", str(exc))
        finally:
            QApplication.restoreOverrideCursor()

    def open_project(self) -> None:
        if not self._confirm_discard_changes():
            return
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Abrir projeto",
            "",
            f"Projetos (*{PROJECT_EXTENSION})",
        )
        if not file_path:
            return
        self._load_project_file(file_path, confirm_discard=False)

    def export_coco(self) -> None:
        if not self.video_manager or not self.project.video_metadata:
            self._show_error("Exportar COCO", "Abra uma mídia ou projeto antes de exportar.")
            return
        dialog = ExportCocoDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        output_dir, mode, json_name = dialog.values()
        if not output_dir:
            self._show_error("Exportar COCO", "Selecione uma pasta de saída.")
            return
        if mode == "annotated":
            frame_indices = [
                frame_index
                for frame_index, annotation in sorted(self.project.annotations.items())
                if annotation.num_keypoints() > 0
            ]
        else:
            frame_indices = sorted(self.project.visited_frames)
        if not frame_indices:
            self._show_error("Exportar COCO", "Não há frames elegíveis para exportação.")
            return
        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            output_json = export_coco_dataset(
                project=self.project,
                skeleton=self._current_skeleton(),
                video_manager=self.video_manager,
                output_dir=output_dir,
                frame_indices=frame_indices,
                json_name=json_name,
            )
            self.statusBar().showMessage(f"COCO exportado em {output_json}")
        except Exception as exc:
            self._show_error("Erro ao exportar COCO", str(exc))
        finally:
            QApplication.restoreOverrideCursor()

    def export_simple_json_file(self) -> None:
        if not self.project.video_metadata:
            self._show_error("Exportar JSON simples", "Abra uma mídia ou projeto antes de exportar.")
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar JSON simples",
            "",
            "JSON (*.json)",
        )
        if not file_path:
            return
        try:
            output = export_simple_json(self.project, self._current_skeleton(), file_path)
            self.statusBar().showMessage(f"JSON simples exportado em {output}")
        except Exception as exc:
            self._show_error("Erro ao exportar JSON simples", str(exc))

    def export_visual_preview(self) -> None:
        if not self.video_manager or not self.project.video_metadata:
            self._show_error("Exportar sequência/vídeo", "Abra uma mídia ou projeto antes de exportar.")
            return
        metadata = self.project.video_metadata
        dialog = ExportVisualDialog(metadata.total_frames, metadata.fps, self)
        dialog.start_spin.setValue(self.current_frame_index)
        dialog.end_spin.setValue(self.current_frame_index)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        output_dir, start_frame, end_frame, export_kind, content_mode, fps = dialog.values()
        if not output_dir:
            self._show_error("Exportar sequência/vídeo", "Selecione uma pasta de saída.")
            return
        if end_frame < start_frame:
            start_frame, end_frame = end_frame, start_frame
        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            output_path = export_visual_sequence(
                project=self.project,
                skeleton=self._current_skeleton(),
                video_manager=self.video_manager,
                output_dir=output_dir,
                start_frame=start_frame,
                end_frame=end_frame,
                export_kind=export_kind,
                content_mode=content_mode,
                show_labels=self.show_labels_checkbox.isChecked(),
                point_radius=float(self.point_radius_spin.value()),
                fps=fps,
                line_width=float(self.line_width_spin.value()),
            )
            self.statusBar().showMessage(f"Prévia exportada em {output_path}")
        except Exception as exc:
            self._show_error("Erro ao exportar sequência/vídeo", str(exc))
        finally:
            QApplication.restoreOverrideCursor()

    def _show_error(self, title: str, message: str) -> None:
        QMessageBox.critical(self, title, message)

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._confirm_discard_changes():
            event.ignore()
            return
        self._pause_video()
        if self.video_manager:
            self.video_manager.cleanup()
        event.accept()
