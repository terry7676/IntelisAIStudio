from __future__ import annotations

import json
import re

from terrygpt.brain.models import PromptTemplate
from terrygpt.database.manager import DatabaseManager, new_id, utc_now


VARIABLE_RE = re.compile(r"{([a-zA-Z_][a-zA-Z0-9_]*)}")


class PromptManager:
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def ensure_defaults(self, system_prompt: str) -> None:
        if self.get_active("intelisai_system") is None:
            self.create("intelisai_system", "system", system_prompt, active=True)

    def create(self, name: str, prompt_type: str, template: str, active: bool = True) -> PromptTemplate:
        clean_name = name.strip()
        clean_template = template.strip()
        if not clean_name:
            raise ValueError("Prompt name cannot be empty.")
        if prompt_type not in {"system", "user", "agent"}:
            raise ValueError("Prompt type must be system, user, or agent.")
        if not clean_template:
            raise ValueError("Prompt template cannot be empty.")
        version = self._next_version(clean_name)
        timestamp = utc_now()
        variables = tuple(sorted(set(VARIABLE_RE.findall(clean_template))))
        with self.database.connect() as connection:
            if active:
                connection.execute("UPDATE prompt_templates SET active = 0 WHERE name = ?", (clean_name,))
            connection.execute(
                """
                INSERT INTO prompt_templates
                    (id, name, prompt_type, version, template, variables_json, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id(),
                    clean_name,
                    prompt_type,
                    version,
                    clean_template,
                    json.dumps(list(variables)),
                    int(active),
                    timestamp,
                    timestamp,
                ),
            )
        return self.get(clean_name, version)

    def get(self, name: str, version: int) -> PromptTemplate:
        row = self.database.fetch_one(
            """
            SELECT id, name, prompt_type, version, template, variables_json, active, created_at, updated_at
            FROM prompt_templates
            WHERE name = ? AND version = ?
            """,
            (name, version),
        )
        if row is None:
            raise KeyError(f"Prompt not found: {name} v{version}")
        return self._from_row(row)

    def get_active(self, name: str) -> PromptTemplate | None:
        row = self.database.fetch_one(
            """
            SELECT id, name, prompt_type, version, template, variables_json, active, created_at, updated_at
            FROM prompt_templates
            WHERE name = ? AND active = 1
            ORDER BY version DESC
            LIMIT 1
            """,
            (name,),
        )
        return None if row is None else self._from_row(row)

    def render(self, name: str, variables: dict[str, object] | None = None) -> str:
        prompt = self.get_active(name)
        if prompt is None:
            raise KeyError(f"No active prompt named {name}")
        values = variables or {}
        missing = [variable for variable in prompt.variables if variable not in values]
        if missing:
            raise ValueError(f"Missing prompt variables: {', '.join(missing)}")
        return prompt.template.format(**values)

    def list(self) -> list[PromptTemplate]:
        rows = self.database.fetch_all(
            """
            SELECT id, name, prompt_type, version, template, variables_json, active, created_at, updated_at
            FROM prompt_templates
            ORDER BY name, version DESC
            """
        )
        return [self._from_row(row) for row in rows]

    def _next_version(self, name: str) -> int:
        row = self.database.fetch_one("SELECT MAX(version) AS version FROM prompt_templates WHERE name = ?", (name,))
        if row is None or row["version"] is None:
            return 1
        return int(row["version"]) + 1

    def _from_row(self, row) -> PromptTemplate:
        return PromptTemplate(
            id=str(row["id"]),
            name=str(row["name"]),
            prompt_type=str(row["prompt_type"]),
            version=int(row["version"]),
            template=str(row["template"]),
            variables=tuple(json.loads(str(row["variables_json"]))),
            active=bool(row["active"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

