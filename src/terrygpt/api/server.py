from __future__ import annotations

import argparse
from pathlib import Path
from typing import Annotated

from terrygpt.config import TerryConfig, load_config
from terrygpt.api.schemas import BrainSettingsRequest, ChatRequest, ImageGenerateRequest, RenameConversationRequest
from terrygpt.brain.manager import AIManager
from terrygpt.core.manager import CoreManager
from terrygpt.media.manager import MediaManager
from terrygpt.services.security import ApiTokenStore

try:
    from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
    import uvicorn
except ModuleNotFoundError as import_error:
    FastAPI = None  # type: ignore[assignment]
    uvicorn = None  # type: ignore[assignment]
    FASTAPI_IMPORT_ERROR = import_error
else:
    FASTAPI_IMPORT_ERROR = None


def create_app(config: TerryConfig | None = None):
    if FASTAPI_IMPORT_ERROR is not None:
        raise RuntimeError("FastAPI dependencies are not installed. Run: python -m pip install -e .") from FASTAPI_IMPORT_ERROR

    active_config = config or load_config()
    core = CoreManager.build()
    core.initialize()
    core.start()

    token_store = ApiTokenStore(active_config.api.token_path)
    token_store.get_or_create_token()

    app = FastAPI(title="TerryGPT API", version="0.1.0")

    def require_auth(authorization: Annotated[str | None, Header()] = None) -> None:
        prefix = "Bearer "
        if authorization is None or not authorization.startswith(prefix):
            raise HTTPException(status_code=401, detail="Missing bearer token.")
        if not token_store.verify(authorization[len(prefix) :]):
            raise HTTPException(status_code=403, detail="Invalid bearer token.")

    @app.get("/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "database_ready": active_config.database.path.exists(),
            "host": active_config.api.host,
            "port": active_config.api.port,
        }

    @app.get("/status", dependencies=[Depends(require_auth)])
    def status() -> dict[str, object]:
        return {"modules": [health.__dict__ for health in core.health_report()]}

    @app.get("/plugins", dependencies=[Depends(require_auth)])
    def plugins() -> dict[str, object]:
        loader = core.module("plugin_loader")
        return {
            "plugins": [
                {
                    "name": record.manifest.name,
                    "version": record.manifest.version,
                    "description": record.manifest.description,
                    "enabled": record.manifest.enabled,
                    "status": record.status,
                    "path": str(record.path),
                    "missing_dependencies": list(record.missing_dependencies),
                }
                for record in getattr(loader, "list_plugins")()
            ]
        }

    @app.get("/events", dependencies=[Depends(require_auth)])
    def events() -> dict[str, object]:
        return {"events": [event.__dict__ for event in core.context.event_bus.history(100)]}

    def ai_manager() -> AIManager:
        module = core.module("ai_manager")
        if not isinstance(module, AIManager):
            raise HTTPException(status_code=500, detail="AI Manager is unavailable.")
        return module

    def media_manager() -> MediaManager:
        module = core.module("media_manager")
        if not isinstance(module, MediaManager):
            raise HTTPException(status_code=500, detail="Media Manager is unavailable.")
        return module

    @app.get("/media/providers", dependencies=[Depends(require_auth)])
    def media_providers() -> dict[str, object]:
        manager = media_manager()
        return {"providers": [provider.__dict__ for provider in manager.list_providers()]}

    @app.get("/media/images", dependencies=[Depends(require_auth)])
    def media_images(limit: int = 20) -> dict[str, object]:
        manager = media_manager()
        return {"images": [image.__dict__ for image in manager.list_recent_images(limit)]}

    @app.post("/media/images/generate", dependencies=[Depends(require_auth)])
    def media_generate_image(request: ImageGenerateRequest) -> dict[str, object]:
        manager = media_manager()
        try:
            result = manager.generate_image(
                request.prompt,
                negative_prompt=request.negative_prompt or "",
                provider_name=request.provider or "",
                seed=request.seed,
                num_inference_steps=request.num_inference_steps,
                guidance_scale=request.guidance_scale,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        payload = result.__dict__.copy()
        payload["output_path"] = str(result.output_path)
        return {"image": payload}

    @app.get("/brain/models", dependencies=[Depends(require_auth)])
    def brain_models() -> dict[str, object]:
        manager = ai_manager()
        return {"models": [model.__dict__ for model in manager.list_models()]}

    @app.post("/brain/models/refresh", dependencies=[Depends(require_auth)])
    def brain_models_refresh() -> dict[str, object]:
        manager = ai_manager()
        return {"models": [model.__dict__ for model in manager.refresh_models()]}

    @app.get("/brain/conversations", dependencies=[Depends(require_auth)])
    def brain_conversations(include_archived: bool = False) -> dict[str, object]:
        manager = ai_manager()
        return {"conversations": [conversation.__dict__ for conversation in manager.list_conversations(include_archived)]}

    @app.post("/brain/conversations", dependencies=[Depends(require_auth)])
    def brain_create_conversation() -> dict[str, object]:
        manager = ai_manager()
        conversation_id = manager.create_conversation()
        return {"conversation_id": conversation_id}

    @app.post("/brain/conversations/{conversation_id}/rename", dependencies=[Depends(require_auth)])
    def brain_rename_conversation(conversation_id: str, request: RenameConversationRequest) -> dict[str, object]:
        manager = ai_manager()
        return {"conversation": manager.rename_conversation(conversation_id, request.title).__dict__}

    @app.post("/brain/conversations/{conversation_id}/archive", dependencies=[Depends(require_auth)])
    def brain_archive_conversation(conversation_id: str) -> dict[str, object]:
        manager = ai_manager()
        return {"conversation": manager.archive_conversation(conversation_id).__dict__}

    @app.post("/brain/conversations/{conversation_id}/restore", dependencies=[Depends(require_auth)])
    def brain_restore_conversation(conversation_id: str) -> dict[str, object]:
        manager = ai_manager()
        return {"conversation": manager.restore_conversation(conversation_id).__dict__}

    @app.delete("/brain/conversations/{conversation_id}", dependencies=[Depends(require_auth)])
    def brain_delete_conversation(conversation_id: str) -> dict[str, object]:
        manager = ai_manager()
        manager.delete_conversation(conversation_id)
        return {"deleted": True}

    @app.post("/brain/chat", dependencies=[Depends(require_auth)])
    def brain_chat(request: ChatRequest) -> dict[str, object]:
        manager = ai_manager()
        if request.model:
            manager.update_settings(default_model=request.model)
        response = manager.complete_response(request.conversation_id, request.message)
        return {"response": response}

    @app.get("/brain/settings", dependencies=[Depends(require_auth)])
    def brain_settings() -> dict[str, object]:
        return {"settings": ai_manager().settings().__dict__}

    @app.post("/brain/settings", dependencies=[Depends(require_auth)])
    def brain_update_settings(request: BrainSettingsRequest) -> dict[str, object]:
        updates = {key: value for key, value in request.model_dump().items() if value is not None}
        return {"settings": ai_manager().update_settings(**updates).__dict__}

    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="terrygpt-server")
    parser.add_argument("--config", help="Path to a TOML config file.")
    args = parser.parse_args(argv)

    config = load_config(config_path=Path(args.config) if args.config else None)
    if uvicorn is None:
        raise SystemExit("FastAPI dependencies are not installed. Run: python -m pip install -e .")

    uvicorn.run(create_app(config), host=config.api.host, port=config.api.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
