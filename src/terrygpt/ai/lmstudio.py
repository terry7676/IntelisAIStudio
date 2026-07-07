from __future__ import annotations

import json
import urllib.request
import urllib.error

from terrygpt.ai.providers import (
    ProviderHealth,
    ProviderMessage,
    ProviderChunk,
    ProviderModelInfo,
)


class LMStudioProvider:
    name = "lmstudio"

    def __init__(self,
                 base_url: str = "http://127.0.0.1:1234",
                 timeout_seconds: int = 120):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def health(self):
        try:
            self.list_models()
            return ProviderHealth(self.name, True, "LM Studio Online")
        except Exception as exc:
            return ProviderHealth(self.name, False, str(exc))

    def list_models(self):
        data = self._json_get("/v1/models")
        return [m["id"] for m in data.get("data", [])]

    def model_details(self):
        data = self._json_get("/v1/models")

        models = []

        for item in data.get("data", []):
            models.append(
                ProviderModelInfo(
                    provider_name="lmstudio",
                    model_name=item["id"],
                    parameter_size="",
                    size_bytes=0,
                    quantization="",
                    context_length=0,
                    metadata=item,
                )
            )

        return models

    def stream_chat(self,
                    model,
                    messages,
                    options):

        payload = {
            "model": model,
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                }
                for m in messages
            ],
            "stream": True,
        }

        request = urllib.request.Request(
            self.base_url + "/v1/chat/completions",
            method="POST",
            headers={
                "Content-Type": "application/json"
            },
            data=json.dumps(payload).encode(),
        )

        with urllib.request.urlopen(
            request,
            timeout=self.timeout_seconds,
        ) as response:

            for raw in response:

                line = raw.decode().strip()

                if not line.startswith("data: "):
                    continue

                line = line[6:]

                if line == "[DONE]":
                    break

                obj = json.loads(line)

                delta = obj["choices"][0]["delta"]

                yield ProviderChunk(
                    content=delta.get("content", ""),
                    done=False,
                )

    def _json_get(self, path):

        request = urllib.request.Request(
            self.base_url + path,
            method="GET",
        )

        with urllib.request.urlopen(
            request,
            timeout=self.timeout_seconds,
        ) as response:

            return json.loads(response.read().decode())