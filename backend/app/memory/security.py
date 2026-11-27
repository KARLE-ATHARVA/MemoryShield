"""Authorization rules for privileged memory operations.

The trusted application layer must authenticate callers before creating
an AuthorizationContext. Never create one from LLM output or request JSON.
"""

from dataclasses import dataclass
from enum import Enum


class ActorRole(str, Enum):
    AGENT = "agent"
    REVIEWER = "reviewer"
    RECOVERY_SERVICE = "recovery_service"


@dataclass(frozen=True)
class AuthorizationContext:
    actor_id: str
    role: ActorRole
    workspace_id: str


class AuthorizationDeniedError(Exception):
    """The caller cannot perform the requested privileged operation."""


def require_authorization(
    actor: AuthorizationContext,
    workspace_id: str,
    allowed_roles: frozenset[ActorRole],
) -> None:
    if not actor.actor_id.strip():
        raise AuthorizationDeniedError("Missing authenticated actor identity.")

    if actor.workspace_id != workspace_id:
        raise AuthorizationDeniedError("Actor is not authorized for this workspace.")

    if actor.role not in allowed_roles:
        raise AuthorizationDeniedError(
            "Actor role is not permitted for this operation."
        )
