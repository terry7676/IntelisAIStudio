from __future__ import annotations

from dataclasses import dataclass

from terrygpt.core.module import BaseModule, ModuleHealth


DANGEROUS_ACTIONS = {
    "delete_file",
    "delete_folder",
    "run_terminal_command",
    "download_executable",
    "install_software",
    "send_email",
    "uninstall_plugin",
}


@dataclass(frozen=True)
class Permission:
    subject: str
    action: str
    allowed: bool


@dataclass(frozen=True)
class ConfirmationRequest:
    action: str
    reason: str
    required: bool


class SecurityManager(BaseModule):
    def __init__(self) -> None:
        super().__init__(name="security")
        self._permissions: dict[tuple[str, str], bool] = {}

    def grant(self, subject: str, action: str) -> None:
        self._permissions[(subject, action)] = True
        self._audit("permission.granted", f"{subject} can {action}")

    def revoke(self, subject: str, action: str) -> None:
        self._permissions[(subject, action)] = False
        self._audit("permission.revoked", f"{subject} cannot {action}")

    def is_allowed(self, subject: str, action: str) -> bool:
        return self._permissions.get((subject, action), False)

    def requires_confirmation(self, action: str) -> bool:
        return action in DANGEROUS_ACTIONS

    def request_confirmation(self, action: str, reason: str) -> ConfirmationRequest:
        request = ConfirmationRequest(action=action, reason=reason, required=self.requires_confirmation(action))
        if self.context is not None:
            self.context.event_bus.publish(
                "security.confirmation.requested",
                request.__dict__,
                source=self.name,
            )
        return request

    def safe_execute(self, subject: str, action: str, confirmed: bool = False) -> None:
        if self.requires_confirmation(action) and not confirmed:
            self._audit("permission.denied", f"{subject} attempted {action} without confirmation")
            raise PermissionError(f"Confirmation is required before {action}.")
        if not self.is_allowed(subject, action) and action not in DANGEROUS_ACTIONS:
            self._audit("permission.denied", f"{subject} attempted unauthorized action {action}")
            raise PermissionError(f"{subject} is not allowed to {action}.")
        self._audit("permission.allowed", f"{subject} can execute {action}")

    def health(self) -> ModuleHealth:
        return ModuleHealth(self.name, self.state, True, f"{len(self._permissions)} permission rule(s)")

    def _audit(self, event_type: str, detail: str) -> None:
        if self.context is not None:
            self.context.event_bus.publish(
                "security.audit",
                {"event_type": event_type, "detail": detail},
                source=self.name,
            )

