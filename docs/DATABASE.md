# Database

## Migration Support

The database creates a `schema_migrations` table.

Each migration has:

1. Version.
2. Name.
3. Applied timestamp.

## Phase 2 Tables

1. `users`
2. `conversations`
3. `messages`
4. `memory`
5. `projects`
6. `tasks`
7. `plugins`
8. `settings`
9. `history`
10. `agents`
11. `audit_logs`
12. `memory_search`
13. `schema_migrations`

## Phase 3 Tables

1. `prompt_templates`
2. `ai_request_logs`
3. `ai_model_cache`
4. `conversation_summaries`
5. `token_usage`

## Phase 3 Conversation Columns

1. `archived_at`
2. `summary`
3. `model_name`
4. `provider_name`
5. `deleted_at`

The migration also repairs older Phase 1 databases that do not yet have `status` or `user_id`.

## Why SQLite

SQLite is local, free, reliable, and simple to back up.

It fits IntelisAi Studio's local-first goal.
