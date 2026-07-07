from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from terrygpt.brain.manager import AIManager
from terrygpt.core.manager import CoreManager
from terrygpt.media.manager import MediaManager
from terrygpt.media.models import ImageGenerationResult
from terrygpt.resources.monitor import ResourceMonitor, ResourceSnapshot
from terrygpt.themes.dark import DARK_STYLESHEET


NAV_ITEMS = (
    "Home",
    "Chat",
    "Agents",
    "Files",
    "Documents",
    "Images",
    "Video",
    "Audio",
    "Automation",
    "Memory",
    "Plugins",
    "Settings",
    "Logs",
)


class BrainChatWorker(QObject):
    chunk = Signal(str)
    finished = Signal(str, str)
    failed = Signal(str)

    def __init__(self, ai_manager: AIManager, conversation_id: str | None, message: str) -> None:
        super().__init__()
        self.ai_manager = ai_manager
        self.conversation_id = conversation_id
        self.message = message
        self.stop_requested = False

    def run(self) -> None:
        final_conversation_id = self.conversation_id or ""
        try:
            for chunk in self.ai_manager.stream_response(self.conversation_id, self.message):
                if self.stop_requested:
                    self.finished.emit(final_conversation_id, "[Stream stopped by user]")
                    return
                if chunk.conversation_id:
                    final_conversation_id = chunk.conversation_id
                if chunk.error:
                    self.failed.emit(chunk.error)
                    return
                if chunk.content:
                    self.chunk.emit(chunk.content)
            self.finished.emit(final_conversation_id, "")
        except Exception as exc:
            self.failed.emit(str(exc))


class ImageGenerationWorker(QObject):
    progress = Signal(int, str, object)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        media_manager: MediaManager,
        prompt: str,
        negative_prompt: str,
        provider_name: str,
    ) -> None:
        super().__init__()
        self.media_manager = media_manager
        self.prompt = prompt
        self.negative_prompt = negative_prompt
        self.provider_name = provider_name

    def run(self) -> None:
        try:
            def on_progress(value: int, message: str, image_bytes: bytes | None = None) -> None:
                self.progress.emit(value, message, image_bytes)

            result = self.media_manager.generate_image(
                self.prompt,
                negative_prompt=self.negative_prompt,
                provider_name=self.provider_name,
                progress_callback=on_progress,
            )
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class VideoGenerationWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        media_manager: MediaManager,
        image_paths: list[Path],
        output_path: Path,
        duration_per_image: float,
    ) -> None:
        super().__init__()
        self.media_manager = media_manager
        self.image_paths = image_paths
        self.output_path = output_path
        self.duration_per_image = duration_per_image

    def run(self) -> None:
        try:
            result = self.media_manager.create_slideshow_video(
                self.image_paths,
                self.output_path,
                duration_per_image=self.duration_per_image,
            )
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class TerryMainWindow(QMainWindow):
    def __init__(self, core: CoreManager) -> None:
        super().__init__()
        self.core = core
        self.ai_manager = core.module("ai_manager")
        if not isinstance(self.ai_manager, AIManager):
            raise RuntimeError("AI Manager is not available.")
        self.media_manager = core.module("media_manager")
        if not isinstance(self.media_manager, MediaManager):
            raise RuntimeError("Media Manager is not available.")
        self.active_conversation_id: str | None = None
        self.chat_thread: QThread | None = None
        self.chat_worker: BrainChatWorker | None = None
        self.image_thread: QThread | None = None
        self.image_worker: ImageGenerationWorker | None = None
        self.notifications: list[str] = []
        self.setWindowTitle("IntelisAi Studio")
        self.resize(1360, 860)
        self.setStyleSheet(DARK_STYLESHEET)

        self.navigation = QListWidget()
        self.navigation.setObjectName("Navigation")
        for item in NAV_ITEMS:
            QListWidgetItem(item, self.navigation)
        self.navigation.currentRowChanged.connect(self._set_page)
        self.navigation.setFixedWidth(190)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._home_page())
        self.pages.addWidget(self._chat_page())
        self.pages.addWidget(self._locked_page("Agents", "Agent execution is not enabled in Phase 2."))
        self.pages.addWidget(self._locked_page("Files", "File tools are not enabled in Phase 2."))
        self.pages.addWidget(self._locked_page("Documents", "Document processing is not enabled in Phase 2."))
        self.pages.addWidget(self._images_page())
        self.pages.addWidget(self._video_page())
        self.pages.addWidget(self._locked_page("Audio", "Audio tools are not enabled in Phase 2."))
        self.pages.addWidget(self._locked_page("Automation", "Automation execution is not enabled in Phase 2."))
        self.pages.addWidget(self._memory_page())
        self.pages.addWidget(self._plugins_page())
        self.pages.addWidget(self._settings_page())
        self.pages.addWidget(self._logs_page())

        splitter = QSplitter()
        splitter.addWidget(self.navigation)
        splitter.addWidget(self.pages)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)

        self.resource_text = QPlainTextEdit()
        self.resource_text.setReadOnly(True)
        self._add_dock("System Monitor", self.resource_text, Qt.DockWidgetArea.RightDockWidgetArea)

        self.notification_text = QPlainTextEdit()
        self.notification_text.setReadOnly(True)
        self._add_dock("Notifications", self.notification_text, Qt.DockWidgetArea.BottomDockWidgetArea)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("IntelisAi Studio running")

        self.core.context.event_bus.subscribe("notification.created", self._on_notification)
        self.core.context.event_bus.subscribe("module.failed", self._on_module_failed)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh_live_status)
        self.timer.start(2000)

        self.navigation.setCurrentRow(0)
        self._refresh_live_status()

    def closeEvent(self, event) -> None:
        self.core.stop()
        super().closeEvent(event)

    def _add_dock(self, title: str, widget: QWidget, area: Qt.DockWidgetArea) -> None:
        dock = QDockWidget(title, self)
        dock.setWidget(widget)
        dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self.addDockWidget(area, dock)

    def _set_page(self, index: int) -> None:
        if index >= 0:
            self.pages.setCurrentIndex(index)

    def _home_page(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        title = QLabel("IntelisAi Studio")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        tabs = QTabWidget()
        tabs.addTab(self._module_status_widget(), "Modules")
        tabs.addTab(self._dependency_widget(), "Startup Checks")
        tabs.addTab(self._event_widget(), "Events")
        layout.addWidget(tabs)
        return root

    def _module_status_widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        self.module_status = QPlainTextEdit()
        self.module_status.setReadOnly(True)
        layout.addWidget(self.module_status)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._refresh_live_status)
        layout.addWidget(refresh)
        return root

    def _dependency_widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        self.dependency_status = QPlainTextEdit()
        self.dependency_status.setReadOnly(True)
        layout.addWidget(self.dependency_status)
        return root

    def _event_widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        self.event_status = QPlainTextEdit()
        self.event_status.setReadOnly(True)
        layout.addWidget(self.event_status)
        return root

    def _locked_page(self, title: str, message: str) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        heading = QLabel(title)
        heading.setObjectName("PageTitle")
        body = QLabel(message)
        body.setObjectName("MutedText")
        body.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(body)
        layout.addStretch(1)
        return root

    def _chat_page(self) -> QWidget:
        root = QWidget()
        layout = QHBoxLayout(root)

        sidebar = QVBoxLayout()
        self.conversation_list = QListWidget()
        self.conversation_list.currentRowChanged.connect(self._select_conversation)
        new_button = QPushButton("New Conversation")
        new_button.clicked.connect(self._new_conversation)
        archive_button = QPushButton("Archive")
        archive_button.clicked.connect(self._archive_conversation)
        sidebar.addWidget(QLabel("Conversations"))
        sidebar.addWidget(self.conversation_list)
        sidebar.addWidget(new_button)
        sidebar.addWidget(archive_button)

        main = QVBoxLayout()
        title = QLabel("Chat")
        title.setObjectName("PageTitle")

        model_row = QHBoxLayout()
        self.model_combo = QComboBox()
        self.model_combo.currentTextChanged.connect(self._select_model)
        refresh_models_button = QPushButton("Refresh Models")
        refresh_models_button.clicked.connect(self._refresh_models)
        model_row.addWidget(QLabel("Model"))
        model_row.addWidget(self.model_combo, 1)
        model_row.addWidget(refresh_models_button)

        self.model_details = QPlainTextEdit()
        self.model_details.setReadOnly(True)
        self.model_details.setMaximumHeight(86)

        self.chat_output = QTextEdit()
        self.chat_output.setReadOnly(True)
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Send a message to IntelisAi Studio (or 'generate image of...' for images)")
        self.chat_input.returnPressed.connect(self._send_or_stop_chat)
        self.send_chat_button = QPushButton("Send")
        self.send_chat_button.clicked.connect(self._send_or_stop_chat)
        self.stop_chat_button = QPushButton("Stop")
        self.stop_chat_button.clicked.connect(self._stop_chat)
        self.stop_chat_button.setVisible(False)

        composer = QHBoxLayout()
        composer.addWidget(self.chat_input, 1)
        composer.addWidget(self.send_chat_button)
        composer.addWidget(self.stop_chat_button)

        main.addWidget(title)
        main.addLayout(model_row)
        main.addWidget(self.model_details)
        main.addWidget(self.chat_output, 1)
        main.addLayout(composer)

        layout.addLayout(sidebar, 1)
        layout.addLayout(main, 4)

        self._refresh_models()
        self._refresh_conversations()
        return root

    def _images_page(self) -> QWidget:
        root = QWidget()
        layout = QHBoxLayout(root)

        sidebar = QVBoxLayout()
        title = QLabel("Images")
        title.setObjectName("PageTitle")
        self.image_gallery = QListWidget()
        self.image_gallery.currentRowChanged.connect(self._select_gallery_image)
        refresh_gallery_button = QPushButton("Refresh Gallery")
        refresh_gallery_button.clicked.connect(self._refresh_image_gallery)
        sidebar.addWidget(title)
        sidebar.addWidget(QLabel("Recent Images"))
        sidebar.addWidget(self.image_gallery, 1)
        sidebar.addWidget(refresh_gallery_button)

        main = QVBoxLayout()
        provider_row = QHBoxLayout()
        self.image_provider_combo = QComboBox()
        refresh_providers_button = QPushButton("Refresh Providers")
        refresh_providers_button.clicked.connect(self._refresh_image_providers)
        provider_row.addWidget(QLabel("Provider"))
        provider_row.addWidget(self.image_provider_combo, 1)
        provider_row.addWidget(refresh_providers_button)

        self.image_prompt = QPlainTextEdit()
        self.image_prompt.setPlaceholderText("Describe the image you want to generate")
        self.image_negative_prompt = QPlainTextEdit()
        self.image_negative_prompt.setPlaceholderText("Optional negative prompt")
        self.image_negative_prompt.setMaximumHeight(72)

        self.image_status = QLabel("Ready")
        self.image_status.setObjectName("MutedText")
        self.image_progress_bar = QProgressBar()
        self.image_progress_bar.setRange(0, 100)
        self.image_progress_bar.setValue(0)
        self.image_progress_bar.setTextVisible(True)
        self.image_preview = QLabel("Generated image preview")
        self.image_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_preview.setMinimumHeight(320)
        self.image_preview.setStyleSheet("border: 1px solid #334155; background: #0f172a;")

        self.generate_image_button = QPushButton("Generate Image")
        self.generate_image_button.clicked.connect(self._generate_image)

        main.addLayout(provider_row)
        main.addWidget(QLabel("Prompt"))
        main.addWidget(self.image_prompt, 1)
        main.addWidget(QLabel("Negative Prompt"))
        main.addWidget(self.image_negative_prompt)
        main.addWidget(self.image_status)
        main.addWidget(self.image_progress_bar)
        main.addWidget(self.image_preview, 2)
        main.addWidget(self.generate_image_button)

        layout.addLayout(sidebar, 1)
        layout.addLayout(main, 3)

        self._refresh_image_providers()
        self._refresh_image_gallery()
        return root

    def _video_page(self) -> QWidget:
        root = QWidget()
        layout = QHBoxLayout(root)

        sidebar = QVBoxLayout()
        title = QLabel("Video")
        title.setObjectName("PageTitle")
        self.video_image_list = QListWidget()
        self.video_image_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        refresh_video_images_button = QPushButton("Refresh Images")
        refresh_video_images_button.clicked.connect(self._refresh_video_images)
        sidebar.addWidget(title)
        sidebar.addWidget(QLabel("Select Images for Video"))
        sidebar.addWidget(self.video_image_list, 1)
        sidebar.addWidget(refresh_video_images_button)

        main = QVBoxLayout()
        self.video_status = QLabel("Ready")
        self.video_status.setObjectName("MutedText")
        self.video_progress_bar = QProgressBar()
        self.video_progress_bar.setRange(0, 100)
        self.video_progress_bar.setValue(0)
        self.video_output_path = QLineEdit()
        self.video_output_path.setPlaceholderText("Output video path")
        self.video_output_path.setText(str(Path("data/media") / "slideshow.mp4"))
        self.video_duration = QLineEdit()
        self.video_duration.setPlaceholderText("Duration per image (seconds)")
        self.video_duration.setText("2.0")
        self.generate_video_button = QPushButton("Create Slideshow Video")
        self.generate_video_button.clicked.connect(self._create_video)

        main.addWidget(QLabel("Video output file"))
        main.addWidget(self.video_output_path)
        main.addWidget(QLabel("Seconds per image"))
        main.addWidget(self.video_duration)
        main.addWidget(self.video_status)
        main.addWidget(self.video_progress_bar)
        main.addWidget(self.generate_video_button)

        layout.addLayout(sidebar, 1)
        layout.addLayout(main, 2)

        self._refresh_video_images()
        return root

    def _refresh_video_images(self) -> None:
        if not hasattr(self, "video_image_list"):
            return
        images = self.media_manager.list_recent_images()
        self.video_image_list.blockSignals(True)
        self.video_image_list.clear()
        for image in images:
            item = QListWidgetItem(image.output_path.name)
            item.setData(Qt.ItemDataRole.UserRole, str(image.output_path))
            self.video_image_list.addItem(item)
        self.video_image_list.blockSignals(False)

    def _create_video(self) -> None:
        selected_items = self.video_image_list.selectedItems()
        if not selected_items:
            self.video_status.setText("Select one or more images first.")
            return

        image_paths = []
        for item in selected_items:
            path = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(path, str):
                image_paths.append(Path(path))

        output_path = Path(self.video_output_path.text().strip())
        if not output_path:
            self.video_status.setText("Enter a valid output path.")
            return
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            duration_per_image = float(self.video_duration.text().strip())
        except ValueError:
            self.video_status.setText("Duration must be a number.")
            return

        self.video_status.setText("Creating video...")
        self._set_video_busy(True)

        self.video_thread = QThread()
        self.video_worker = VideoGenerationWorker(
            self.media_manager,
            image_paths,
            output_path,
            duration_per_image,
        )
        self.video_worker.moveToThread(self.video_thread)
        self.video_thread.started.connect(self.video_worker.run)
        self.video_worker.finished.connect(self._video_finished)
        self.video_worker.failed.connect(self._video_failed)
        self.video_worker.finished.connect(self.video_thread.quit)
        self.video_worker.failed.connect(self.video_thread.quit)
        self.video_worker.finished.connect(self.video_worker.deleteLater)
        self.video_worker.failed.connect(self.video_worker.deleteLater)
        self.video_thread.finished.connect(self.video_thread.deleteLater)
        self.video_thread.start()

    def _video_finished(self, result: object) -> None:
        if isinstance(result, dict) and "output_path" in result:
            self.video_status.setText(f"Saved video to {result['output_path']}")
        else:
            self.video_status.setText("Video creation completed.")
        self.video_progress_bar.setValue(100)
        self._set_video_busy(False)

    def _video_failed(self, message: str) -> None:
        self.video_status.setText(f"Error: {message}")
        self.video_progress_bar.setValue(0)
        self._set_video_busy(False)

    def _set_video_busy(self, busy: bool) -> None:
        self.generate_video_button.setDisabled(busy)
        self.video_image_list.setDisabled(busy)
        self.video_output_path.setDisabled(busy)
        self.video_duration.setDisabled(busy)
        if not busy:
            self.video_progress_bar.setValue(0)

    def _memory_page(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        title = QLabel("Memory Engine")
        title.setObjectName("PageTitle")
        self.memory_status = QPlainTextEdit()
        self.memory_status.setReadOnly(True)
        layout.addWidget(title)
        layout.addWidget(self.memory_status)
        return root

    def _plugins_page(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        title = QLabel("Plugin System")
        title.setObjectName("PageTitle")
        self.plugin_status = QPlainTextEdit()
        self.plugin_status.setReadOnly(True)
        layout.addWidget(title)
        layout.addWidget(self.plugin_status)
        return root

    def _settings_page(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        title = QLabel("Settings")
        title.setObjectName("PageTitle")
        self.settings_status = QPlainTextEdit()
        self.settings_status.setReadOnly(True)
        layout.addWidget(title)
        layout.addWidget(self.settings_status)
        return root

    def _logs_page(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        title = QLabel("Logs")
        title.setObjectName("PageTitle")
        self.logs_status = QTextEdit()
        self.logs_status.setReadOnly(True)
        layout.addWidget(title)
        layout.addWidget(self.logs_status)
        return root

    def _refresh_live_status(self) -> None:
        health = self.core.health_report()
        self.module_status.setPlainText("\n".join(f"{item.name}: {item.state} - {item.detail}" for item in health))
        self.event_status.setPlainText(
            "\n".join(f"{event.created_at} {event.source} {event.event_type}" for event in self.core.context.event_bus.history(40))
        )
        self._refresh_dependencies()
        self._refresh_resources()
        self._refresh_plugins()
        self._refresh_settings()
        self._refresh_memory()
        self._refresh_logs()

    def _refresh_dependencies(self) -> None:
        module = self.core.module("dependency_checker")
        statuses = getattr(module, "statuses", [])
        self.dependency_status.setPlainText(
            "\n".join(f"{status.name}: {'OK' if status.available else 'Missing'} - {status.detail}" for status in statuses)
        )

    def _refresh_resources(self) -> None:
        module = self.core.module("resource_monitor")
        if isinstance(module, ResourceMonitor):
            snapshot = module.snapshot()
        else:
            snapshot = ResourceSnapshot(None, None, None, None, None, None, None, None, None, None)
        self.resource_text.setPlainText(
            "\n".join(
                [
                    f"CPU: {self._value(snapshot.cpu_percent, '%')}",
                    f"RAM: {self._value(snapshot.ram_used_mb, ' MB')} / {self._value(snapshot.ram_total_mb, ' MB')}",
                    f"Disk: {self._value(snapshot.disk_used_gb, ' GB')} / {self._value(snapshot.disk_total_gb, ' GB')}",
                    f"Network RX: {self._value(snapshot.network_received_mb, ' MB')}",
                    f"Network TX: {self._value(snapshot.network_sent_mb, ' MB')}",
                    f"GPU: {self._value(snapshot.gpu_percent, '%')}",
                    f"GPU RAM: {self._value(snapshot.gpu_memory_used_mb, ' MB')} / {self._value(snapshot.gpu_memory_total_mb, ' MB')}",
                ]
            )
        )

    def _refresh_plugins(self) -> None:
        module = self.core.module("plugin_loader")
        records = getattr(module, "list_plugins")()
        self.plugin_status.setPlainText(
            "\n\n".join(
                f"{record.manifest.name} {record.manifest.version}\nStatus: {record.status}\n{record.manifest.description}"
                for record in records
            )
            or "No plugins detected."
        )

    def _refresh_settings(self) -> None:
        module = self.core.module("configuration")
        categories = ["ai", "hardware", "preferences", "plugins", "security", "theme", "voice", "media"]
        lines = []
        for category in categories:
            settings = getattr(module, "get_category")(category)
            lines.append(f"[{category}]")
            lines.extend(f"{key}: {value}" for key, value in settings.items())
            lines.append("")
        self.settings_status.setPlainText("\n".join(lines))

    def _refresh_memory(self) -> None:
        module = self.core.module("memory_engine")
        self.memory_status.setPlainText(module.health().detail)

    def _refresh_models(self) -> None:
        if not hasattr(self, "model_combo"):
            return
        current = self.model_combo.currentText()
        models = self.ai_manager.refresh_models()
        if not models:
            models = self.ai_manager.list_models()
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        for model in models:
            self.model_combo.addItem(model.model_name)
        if current:
            index = self.model_combo.findText(current)
            if index >= 0:
                self.model_combo.setCurrentIndex(index)
        self.model_combo.blockSignals(False)
        self._update_model_details()

    def _select_model(self, model_name: str) -> None:
        if model_name:
            self.ai_manager.update_settings(default_model=model_name)
        self._update_model_details()

    def _update_model_details(self) -> None:
        if not hasattr(self, "model_details"):
            return
        selected = self.model_combo.currentText() if hasattr(self, "model_combo") else ""
        for model in self.ai_manager.list_models():
            if model.model_name == selected:
                self.model_details.setPlainText(
                    "\n".join(
                        [
                            f"Name: {model.model_name}",
                            f"Parameters: {model.parameter_size or 'Unknown'}",
                            f"Size: {model.display_size}",
                            f"Quantization: {model.quantization or 'Unknown'}",
                            f"Context length: {model.context_length or 'Unknown'}",
                        ]
                    )
                )
                return
        self.model_details.setPlainText("No Ollama model detected. Install a model, then refresh models.")

    def _refresh_conversations(self) -> None:
        if not hasattr(self, "conversation_list"):
            return
        conversations = self.ai_manager.list_conversations(include_archived=False)
        self.conversation_list.blockSignals(True)
        self.conversation_list.clear()
        for conversation in conversations:
            item = QListWidgetItem(conversation.title)
            item.setData(Qt.ItemDataRole.UserRole, conversation.id)
            self.conversation_list.addItem(item)
        self.conversation_list.blockSignals(False)

    def _new_conversation(self) -> None:
        self.active_conversation_id = self.ai_manager.create_conversation("New chat")
        self.chat_output.clear()
        self._refresh_conversations()

    def _archive_conversation(self) -> None:
        if self.active_conversation_id:
            self.ai_manager.archive_conversation(self.active_conversation_id)
            self.active_conversation_id = None
            self.chat_output.clear()
            self._refresh_conversations()

    def _select_conversation(self, row: int) -> None:
        item = self.conversation_list.item(row)
        if item is None:
            return
        conversation_id = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(conversation_id, str):
            return
        self.active_conversation_id = conversation_id
        self.chat_output.clear()
        for message in self.ai_manager.messages(conversation_id):
            speaker = "You" if message.role == "user" else "IntelisAi Studio"
            self.chat_output.append(f"<b>{speaker}:</b> {message.content}")

    def _send_or_stop_chat(self) -> None:
        if self.send_chat_button.text() == "Send":
            self._send_chat_message()
        else:
            self._stop_chat()

    def _stop_chat(self) -> None:
        if self.chat_thread and self.chat_thread.isRunning():
            if self.chat_worker:
                self.chat_worker.stop_requested = True
            self.chat_thread.quit()
            self.chat_thread.wait()
        self._set_chat_busy(False)

    def _send_chat_message(self) -> None:
        text = self.chat_input.text().strip()
        if not text:
            return
        self.chat_input.clear()
        self.chat_output.append(f"<b>You:</b> {text}")
        self.chat_output.append("<b>IntelisAi Studio:</b> ")
        self._set_chat_busy(True)

        self.chat_thread = QThread()
        self.chat_worker = BrainChatWorker(self.ai_manager, self.active_conversation_id, text)
        self.chat_worker.moveToThread(self.chat_thread)
        self.chat_thread.started.connect(self.chat_worker.run)
        self.chat_worker.chunk.connect(self._append_chat_chunk)
        self.chat_worker.finished.connect(self._chat_finished)
        self.chat_worker.failed.connect(self._chat_failed)
        self.chat_worker.finished.connect(self.chat_thread.quit)
        self.chat_worker.failed.connect(self.chat_thread.quit)
        self.chat_worker.finished.connect(self.chat_worker.deleteLater)
        self.chat_worker.failed.connect(self.chat_worker.deleteLater)
        self.chat_thread.finished.connect(self.chat_thread.deleteLater)
        self.chat_thread.start()

    def _append_chat_chunk(self, chunk: str) -> None:
        cursor = self.chat_output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(chunk)
        self.chat_output.setTextCursor(cursor)

    def _chat_finished(self, conversation_id: str, _message: str) -> None:
        if conversation_id:
            self.active_conversation_id = conversation_id
        self._set_chat_busy(False)
        self._refresh_conversations()

    def _chat_failed(self, message: str) -> None:
        self.chat_output.append(f"<b>Error:</b> {message}")
        self._set_chat_busy(False)

    def _set_chat_busy(self, busy: bool) -> None:
        self.chat_input.setDisabled(busy)
        if busy:
            self.send_chat_button.setVisible(False)
            self.stop_chat_button.setVisible(True)
            self.send_chat_button.setText("Send")
        else:
            self.send_chat_button.setVisible(True)
            self.stop_chat_button.setVisible(False)

    def _refresh_image_providers(self) -> None:
        if not hasattr(self, "image_provider_combo"):
            return
        current = self.image_provider_combo.currentText()
        providers = self.media_manager.list_providers()
        self.image_provider_combo.blockSignals(True)
        self.image_provider_combo.clear()
        for provider in providers:
            label = provider.name if provider.available else f"{provider.name} (unavailable)"
            self.image_provider_combo.addItem(label, provider.name)
        if current:
            index = self.image_provider_combo.findData(current)
            if index >= 0:
                self.image_provider_combo.setCurrentIndex(index)
        self.image_provider_combo.blockSignals(False)

    def _refresh_image_gallery(self) -> None:
        if not hasattr(self, "image_gallery"):
            return
        images = self.media_manager.list_recent_images()
        self.image_gallery.blockSignals(True)
        self.image_gallery.clear()
        for image in images:
            item = QListWidgetItem(image.output_path.name)
            item.setData(Qt.ItemDataRole.UserRole, str(image.output_path))
            self.image_gallery.addItem(item)
        self.image_gallery.blockSignals(False)

    def _select_gallery_image(self, row: int) -> None:
        item = self.image_gallery.item(row)
        if item is None:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(path, str):
            self._show_image_preview(Path(path))

    def _generate_image(self) -> None:
        prompt = self.image_prompt.toPlainText().strip()
        if not prompt:
            self.image_status.setText("Enter a prompt before generating.")
            return

        provider_name = self.image_provider_combo.currentData()
        if not isinstance(provider_name, str) or not provider_name:
            self.image_status.setText("Select an image provider.")
            return

        self.image_status.setText("Generating image...")
        self.image_progress_bar.setValue(0)
        self.image_preview.setText("Rendering preview...")
        self._set_image_busy(True)

        self.image_thread = QThread()
        self.image_worker = ImageGenerationWorker(
            self.media_manager,
            prompt,
            self.image_negative_prompt.toPlainText().strip(),
            provider_name,
        )
        self.image_worker.moveToThread(self.image_thread)
        self.image_thread.started.connect(self.image_worker.run)
        self.image_worker.progress.connect(self._update_image_progress)
        self.image_worker.finished.connect(self._image_finished)
        self.image_worker.failed.connect(self._image_failed)
        self.image_worker.finished.connect(self.image_thread.quit)
        self.image_worker.failed.connect(self.image_thread.quit)
        self.image_worker.finished.connect(self.image_worker.deleteLater)
        self.image_worker.failed.connect(self.image_worker.deleteLater)
        self.image_thread.finished.connect(self.image_thread.deleteLater)
        self.image_thread.start()

    def _update_image_progress(self, value: int, message: str, image_data: object) -> None:
        self.image_progress_bar.setValue(max(0, min(100, value)))
        self.image_status.setText(message)
        if isinstance(image_data, (bytes, bytearray)) and image_data:
            pixmap = QPixmap()
            if pixmap.loadFromData(image_data):
                scaled = pixmap.scaled(
                    self.image_preview.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.image_preview.setPixmap(scaled)

    def _image_finished(self, result: object) -> None:
        self.image_progress_bar.setValue(100)
        if isinstance(result, ImageGenerationResult):
            self.image_status.setText(f"Saved to {result.output_path}")
            self._show_image_preview(result.output_path)
            self._refresh_image_gallery()
        self._set_image_busy(False)

    def _image_failed(self, message: str) -> None:
        self.image_progress_bar.setValue(0)
        self.image_status.setText(f"Error: {message}")
        self._set_image_busy(False)

    def _show_image_preview(self, path: Path) -> None:
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.image_preview.setText(f"Could not load image: {path}")
            return
        scaled = pixmap.scaled(
            self.image_preview.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_preview.setPixmap(scaled)

    def _set_image_busy(self, busy: bool) -> None:
        self.generate_image_button.setDisabled(busy)
        self.image_prompt.setDisabled(busy)
        self.image_negative_prompt.setDisabled(busy)
        self.image_provider_combo.setDisabled(busy)
        if not busy:
            self.image_progress_bar.setValue(0)

    def _refresh_logs(self) -> None:
        log_dir = self.core.context.config.logging.path.parent
        lines = []
        for path in sorted(Path(log_dir).glob("*.log")):
            lines.append(f"{path.name}")
            try:
                content = path.read_text(encoding="utf-8").splitlines()[-8:]
            except OSError as exc:
                content = [str(exc)]
            lines.extend(content)
            lines.append("")
        self.logs_status.setPlainText("\n".join(lines))

    def _on_notification(self, event: object) -> None:
        payload = getattr(event, "payload", {})
        self.notifications.append(str(payload.get("message", payload)))
        self.notification_text.setPlainText("\n".join(self.notifications[-50:]))

    def _on_module_failed(self, event: object) -> None:
        payload = getattr(event, "payload", {})
        self.notifications.append(f"Module failure: {payload}")
        self.notification_text.setPlainText("\n".join(self.notifications[-50:]))

    def _value(self, value: object, suffix: str) -> str:
        if value is None:
            return "Unavailable"
        return f"{value}{suffix}"
