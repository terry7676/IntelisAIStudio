# Phase 1 API

## Local Address

The default API address is:

```text
http://127.0.0.1:8765
```

## Open Route

`GET /health`

This checks whether the API process is running.

## Protected Routes

These routes require:

```text
Authorization: Bearer YOUR_LOCAL_TOKEN
```

The token is created by IntelisAi Studio using:

```powershell
python -m terrygpt init
```

The token file is:

```text
data/secrets.toml
```

Protected Phase 2 routes:

1. `GET /status`
2. `GET /plugins`
3. `GET /events`

## Brain Routes

These routes were added in Phase 3:

1. `GET /brain/models`
2. `POST /brain/models/refresh`
3. `GET /brain/conversations`
4. `POST /brain/conversations`
5. `POST /brain/conversations/{conversation_id}/rename`
6. `POST /brain/conversations/{conversation_id}/archive`
7. `POST /brain/conversations/{conversation_id}/restore`
8. `DELETE /brain/conversations/{conversation_id}`
9. `POST /brain/chat`
10. `GET /brain/settings`
11. `POST /brain/settings`

All Brain routes go through the AI Manager.
