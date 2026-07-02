from __future__ import annotations

import json

from terrygpt.ai.providers import AIProviderRegistry, ProviderModelInfo
from terrygpt.brain.models import ModelInfo
from terrygpt.database.manager import DatabaseManager, new_id, utc_now


class ModelManager:
    def __init__(self, database: DatabaseManager, providers: AIProviderRegistry) -> None:
        self.database = database
        self.providers = providers
        self._cache: dict[tuple[str, str], ModelInfo] = {}

    def refresh(self) -> list[ModelInfo]:
        models: list[ModelInfo] = []
        for provider_name in self.providers.list_providers():
            provider = self.providers.provider(provider_name)
            try:
                provider_models = provider.model_details()
            except Exception:
                provider_models = []
            for provider_model in provider_models:
                model = self._from_provider_model(provider_model)
                self._cache[(model.provider_name, model.model_name)] = model
                self._persist(model)
                models.append(model)
        return models

    def list(self, refresh: bool = False) -> list[ModelInfo]:
        if refresh or not self._cache:
            refreshed = self.refresh()
            if refreshed:
                return refreshed
            self._load_from_database()
        return sorted(self._cache.values(), key=lambda item: (item.provider_name, item.model_name))

    def choose(self, provider_name: str, requested_model: str | None = None) -> ModelInfo | None:
        models = [model for model in self.list(refresh=False) if model.provider_name == provider_name]
        if requested_model:
            for model in models:
                if model.model_name == requested_model:
                    return model
        if models:
            return models[0]
        refreshed = self.list(refresh=True)
        provider_models = [model for model in refreshed if model.provider_name == provider_name]
        if requested_model:
            for model in provider_models:
                if model.model_name == requested_model:
                    return model
        return provider_models[0] if provider_models else None

    def _from_provider_model(self, provider_model: ProviderModelInfo) -> ModelInfo:
        return ModelInfo(
            provider_name=provider_model.provider_name,
            model_name=provider_model.model_name,
            parameter_size=provider_model.parameter_size,
            size_bytes=provider_model.size_bytes,
            quantization=provider_model.quantization,
            context_length=provider_model.context_length,
            metadata=provider_model.metadata,
        )

    def _persist(self, model: ModelInfo) -> None:
        timestamp = utc_now()
        with self.database.connect() as connection:
            existing = connection.execute(
                "SELECT id FROM ai_model_cache WHERE provider_name = ? AND model_name = ?",
                (model.provider_name, model.model_name),
            ).fetchone()
            model_id = str(existing["id"]) if existing else new_id()
            connection.execute(
                """
                INSERT INTO ai_model_cache
                    (id, provider_name, model_name, parameter_size, size_bytes, quantization,
                     context_length, metadata_json, detected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider_name, model_name) DO UPDATE SET
                    parameter_size = excluded.parameter_size,
                    size_bytes = excluded.size_bytes,
                    quantization = excluded.quantization,
                    context_length = excluded.context_length,
                    metadata_json = excluded.metadata_json,
                    detected_at = excluded.detected_at
                """,
                (
                    model_id,
                    model.provider_name,
                    model.model_name,
                    model.parameter_size,
                    model.size_bytes,
                    model.quantization,
                    model.context_length,
                    json.dumps(model.metadata, sort_keys=True),
                    timestamp,
                ),
            )

    def _load_from_database(self) -> None:
        rows = self.database.fetch_all(
            """
            SELECT provider_name, model_name, parameter_size, size_bytes, quantization, context_length, metadata_json
            FROM ai_model_cache
            ORDER BY provider_name, model_name
            """
        )
        for row in rows:
            model = ModelInfo(
                provider_name=str(row["provider_name"]),
                model_name=str(row["model_name"]),
                parameter_size=str(row["parameter_size"]),
                size_bytes=int(row["size_bytes"]),
                quantization=str(row["quantization"]),
                context_length=int(row["context_length"]),
                metadata=json.loads(str(row["metadata_json"])),
            )
            self._cache[(model.provider_name, model.model_name)] = model

