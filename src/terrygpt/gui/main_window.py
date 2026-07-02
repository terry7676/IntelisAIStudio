from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
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

    def run(self) -> None:
        final_conversation_id = self.conversation_id or ""
        try:
            for chunk in self.ai_manager.stream_response(self.conversation_id, self.message):
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


class TerryMainWindow(QMainWindow):
    def __init__(self, core: CoreManager) -> None:
        super().__init__()
        self.core = core
        self.ai_manager = core.module("ai_manager")
        if not isinstance(self.ai_manager, AIManager):
            raise RuntimeError("AI Manager is not available.")
        self.active_conversation_id: str | None = None
        self.chat_thread: QThread | None = None
        self.chat_worker: BrainChatWorker | None = None
        self.notifications: list[str] = []
        self.setWindowTitle("TerryGPT Core Engine")
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
        self.pages.addWidget(self._locked_page("Images", "Image tools are not enabled in Phase 2."))
        self.pages.addWidget(self._locked_page("Video", "Video tools are not enabled in Phase 2."))
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
        self.statusBar().showMessage("TerryGPT Core Engine running")

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
        title = QLabel("TerryGPT Core Engine")
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
        self.chat_input.setPlaceholderText("Send a message to TerryGPT")
        self.chat_input.returnPressed.connect(self._send_chat_message)
        self.send_chat_button = QPushButton("Send")
        self.send_chat_button.clicked.connect(self._send_chat_message)

        composer = QHBoxLayout()
        composer.addWidget(self.chat_input, 1)
        composer.addWidget(self.send_chat_button)

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
        categories = ["ai", "hardware", "preferences", "plugins", "security", "theme", "voice"]
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
            speaker = "You" if message.role == "user" else "TerryGPT"
            self.chat_output.append(f"<b>{speaker}:</b> {message.content}")

    def _send_chat_message(self) -> None:
        text = self.chat_input.text().strip()
        if not text:
            return
        self.chat_input.clear()
        self.chat_output.append(f"<b>You:</b> {text}")
        self.chat_output.append("<b>TerryGPT:</b> ")
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
        self.send_chat_button.setDisabled(busy)

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
