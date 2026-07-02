# Phase 2 Scope

## Built

1. Core Manager.
2. Event Bus.
3. Configuration Manager.
4. Logger.
5. Database migrations.
6. Memory Engine.
7. AI Provider Layer.
8. Plugin Loader.
9. Task Scheduler.
10. Security Manager.
11. Resource Monitor.
12. Desktop shell.
13. Tests for major subsystems.

## Not Built

1. User-facing AI chat.
2. Vision.
3. Audio tools.
4. Video tools.
5. Automation execution.
6. Computer control.

## Run

```powershell
python main.py
```

## Verify Core Only

```powershell
python main.py --no-gui
python -m unittest discover tests
```

