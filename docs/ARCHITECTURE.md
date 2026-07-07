# IntelisAi Studio Phase 1 Architecture

## Layers

1. Desktop UI: `src/terrygpt/desktop`
2. API layer: `src/terrygpt/api`
3. Services: `src/terrygpt/services`
4. Database: `src/terrygpt/database.py`
5. Configuration: `src/terrygpt/config.py`
6. Plugins: `plugins`

## Chat Flow

1. The user sends a message.
2. IntelisAi Studio saves the user message in SQLite.
3. IntelisAi Studio sends the conversation to Ollama.
4. Ollama streams chunks back.
5. IntelisAi Studio shows the chunks in the desktop app or API.
6. IntelisAi Studio saves the assistant message.
7. IntelisAi Studio stores a searchable memory record.

## API Flow

1. `/health` is open for local status checks.
2. Other routes require a bearer token.
3. The token is stored in `data/secrets.toml`.
4. The default host is `127.0.0.1`.

## Plugin Flow

1. Each plugin has a folder.
2. Each plugin folder contains `manifest.json`.
3. Each plugin folder contains `plugin.py`.
4. `plugin.py` exposes `create_plugin()`.
5. The plugin returns command functions.
6. IntelisAi Studio can list and run those commands.

