# TerryGPT

TerryGPT is a local-first AI operating system project for Windows.

Phase 3 adds the TerryGPT Brain. It is not the full operating system yet.

## What Phase 2 Includes

1. Python package structure.
2. Core Manager.
3. Event Bus.
4. Persistent configuration manager.
5. Rotating category logs.
6. SQLite database migrations.
7. Long-term memory engine.
8. AI provider interface with Ollama detection.
9. Dynamic plugin loader.
10. Background task scheduler.
11. Security manager.
12. Resource monitor.
13. PySide6 desktop shell.
14. Unit tests.
15. Beginner setup instructions.

## What Phase 3 Adds

1. AI Manager.
2. Conversation Manager.
3. Model Manager.
4. Prompt Manager.
5. Context Builder.
6. Response pipeline.
7. AI request logging.
8. Token usage tracking.
9. Ollama model metadata detection.
10. Streaming responses in the desktop Chat page.
11. Automatic memory integration.
12. Error recovery when the provider fails.

## What Phase 2 Does Not Include

1. Android app.
2. Video processing.
3. Computer control.
4. Voice conversations.
5. Vector database memory backend.
6. Automatic updates.
7. Installer.
8. Voice, vision, OCR, video, browser, agents, Android, and automation.

Those belong in later phases.

## Folder Map

1. `main.py` starts TerryGPT.
2. `src/terrygpt/app` starts the application.
3. `src/terrygpt/core` contains the Core Manager and Event Bus.
4. `src/terrygpt/configuration` stores persistent runtime settings.
5. `src/terrygpt/database` owns SQLite migrations and repositories.
6. `src/terrygpt/logging` owns rotating logs.
7. `src/terrygpt/memory` owns long-term memory.
8. `src/terrygpt/ai` owns provider interfaces.
9. `src/terrygpt/plugins` owns plugin detection and lifecycle.
10. `src/terrygpt/tasks` owns background task scheduling.
11. `src/terrygpt/security` owns permissions and confirmations.
12. `src/terrygpt/resources` tracks CPU, RAM, disk, network, and GPU.
13. `src/terrygpt/gui` contains the desktop shell.
14. `config/default.toml` contains default settings.
15. `plugins` contains installable plugins.
16. `tests` contains verification tests.
17. `docs` contains architecture and security notes.
18. `data` is created when TerryGPT runs.
19. `src/terrygpt/brain` contains the intelligence layer.

## Setup

1. Open PowerShell.
2. Go to this folder:

```powershell
cd C:\Users\thill\Documents\Codex\2026-07-01\br\outputs\TerryGPT
```

3. Check Python:

```powershell
python --version
```

4. Create a virtual environment:

```powershell
python -m venv .venv
```

5. Turn it on:

```powershell
.\.venv\Scripts\Activate.ps1
```

6. Install TerryGPT:

```powershell
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

7. Make sure Ollama is running and has at least one local model installed.

8. Start TerryGPT:

```powershell
python main.py
```

9. Start only the Core Engine without opening the GUI:

```powershell
python main.py --no-gui
```

## Start the Desktop App

```powershell
python main.py
```

The Chat tab streams responses through the AI Manager.

## Start the API

```powershell
python -m terrygpt server
```

The health URL is:

```text
http://127.0.0.1:8765/health
```

Protected API routes require a bearer token. TerryGPT creates it in:

```text
data/secrets.toml
```

Do not share that file.

## Run Tests

```powershell
python -m unittest discover tests
```

## Current Verification

The current test suite covers:

1. Event Bus.
2. Core Manager.
3. Configuration Manager.
4. Database migrations.
5. Memory Engine.
6. Plugin Loader.
7. Task Scheduler.
8. Security Manager.
9. Resource Monitor.

## Plugin Test

The sample plugin lives here:

```text
plugins/hello_terry
```

It proves that TerryGPT can load a plugin without changing the main code.
