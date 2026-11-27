"""Memory Gateway — workspace-scoped claim and generation operations.

This is the single controlled entry point for all persistent-memory writes
and reads.  Every operation is scoped to an explicitly resolved workspace;
callers never supply raw workspace database IDs directly.

Responsibilities
----------------
- Resolve a workspace by its application-level ``workspace_key``.
- Create claims bound to that workspace.
- Retrieve claims within that workspace only.
- Create memory generations bound to that workspace.
- Build a candidate generation from existing eligible claim versions.
- Activate a candidate generation (workspace-scoped, with optimistic lock).
- Reject any attempt to reference a generation or claim from a different
  workspace.

Trust and policy
----------------
The gateway calls ``MemoryTrustPolicy.evaluate`` before activating a
generation.  It does **not** call the policy for ingestion — ingestion is
always permitted (the policy returns ``allowed=True`` for INGEST), but the
gateway still records source provenance so forensics can trace the write.

Quarantine filter
-----------------
Normal retrieval excludes claim versions with ``visibility_status``
of ``'quarantined'`` or ``'superseded'``.  The gateway enforces this on
every read path that returns claim versions to the agent.

Concurrency
-----------
Workspace activation uses an optimistic lock on ``MemoryWorkspace.revision``.
If the revision has changed between read and write the activation raises
``StaleWorkspaceError`` and the caller must retry.

Domain independence
-------------------
No supplier names, field keys, or domain-specific constants appear here.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import (
    Claim,
    ClaimVersion,
    GenerationClaimVersion,
    MemoryGeneration,
    MemorySecurityAudit,
    MemoryWorkspace,
    Source,
)
from app.memory.policy import (
    POLICY_VERSION,
    MemoryPolicyContext,
    MemoryTrustPolicy,
    Operation,
    TrustLevel,
)
from app.memory.security import (
    ActorRole,
    AuthorizationContext,
    AuthorizationDeniedError,
    require_authorization,
)

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class WorkspaceNotFoundError(Exception):
    """Raised when a workspace_key does not match any known workspace."""


class CrossWorkspaceError(Exception):
    """Raised when an operation attempts to mix records from different workspaces."""


class StaleWorkspaceError(Exception):
    """Raised when an optimistic-lock mismatch is detected during activation."""


class PolicyDeniedError(Exception):
    """Raised when ``MemoryTrustPolicy`` rejects the requested operation."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# ---------------------------------------------------------------------------
# Context object
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WorkspaceContext:
    """Resolved workspace identity passed to every gateway operation.

    Instances are created by ``MemoryGateway.resolve_workspace`` and must
    not be constructed by untrusted callers with an arbitrary ``workspace_id``.
    """

    workspace_key: str
    workspace_id: str


# ---------------------------------------------------------------------------
# Gateway
# ---------------------------------------------------------------------------


class MemoryGateway:
    """Workspace-scoped memory gateway.

    Parameters
    ----------
    session:
        An active SQLAlchemy ``Session``.  The gateway does not manage
        transaction boundaries; callers are responsible for commit/rollback.
    policy:
        Optional policy evaluator.  Defaults to ``MemoryTrustPolicy()``.
    """

    def __init__(
        self,
        session: Session,
        policy: MemoryTrustPolicy | None = None,
    ) -> None:
        self._session = session
        self._policy = policy or MemoryTrustPolicy()

    # ------------------------------------------------------------------
    # Workspace resolution
    # ------------------------------------------------------------------

    def resolve_workspace(self, workspace_key: str) -> WorkspaceContext:
        """Return a ``WorkspaceContext`` for the given key.

        Raises ``WorkspaceNotFoundError`` if no matching workspace exists.
        The returned context is the only safe way to obtain a ``workspace_id``
        for subsequent gateway operations.
        """
        ws = self._session.scalar(
            select(MemoryWorkspace).where(
                MemoryWorkspace.workspace_key == workspace_key
            )
        )
        if ws is None:
            raise WorkspaceNotFoundError(
                f"No workspace found for key '{workspace_key}'."
            )
        return WorkspaceContext(
            workspace_key=ws.workspace_key,
            workspace_id=ws.id,
        )

    def get_or_create_workspace(self, workspace_key: str) -> WorkspaceContext:
        """Return a ``WorkspaceContext``, creating the workspace if absent.

        This is a convenience helper for test setup and first-run
        initialisation.  Production callers should prefer
        ``resolve_workspace`` after explicit workspace provisioning.
        """
        ws = self._session.scalar(
            select(MemoryWorkspace).where(
                MemoryWorkspace.workspace_key == workspace_key
            )
        )
        if ws is None:
            ws = MemoryWorkspace(workspace_key=workspace_key)
            self._session.add(ws)
            self._session.flush()

        return WorkspaceContext(
            workspace_key=ws.workspace_key,
            workspace_id=ws.id,
        )

    # ------------------------------------------------------------------
    # Claim operations
    # ------------------------------------------------------------------

    def get_or_create_claim(
        self,
        ctx: WorkspaceContext,
        subject_key: str,
        field_key: str,
    ) -> Claim:
        """Return the existing claim or create a new one for this workspace.

        The claim is scoped to ``ctx.workspace_id``; the same
        ``(subject_key, field_key)`` pair in a different workspace is an
        independent claim.
        """
        claim = self._session.scalar(
            select(Claim).where(
                Claim.workspace_id == ctx.workspace_id,
                Claim.subject_key == subject_key,
                Claim.field_key == field_key,
            )
        )
        if claim is None:
            claim = Claim(
                workspace_id=ctx.workspace_id,
                subject_key=subject_key,
                field_key=field_key,
            )
            self._session.add(claim)
            self._session.flush()

        return claim

    def get_eligible_versions(
        self,
        ctx: WorkspaceContext,
        subject_key: str | None = None,
        field_key: str | None = None,
    ) -> list[ClaimVersion]:
        """Return eligible (non-quarantined, non-superseded) claim versions.

        Results are scoped to ``ctx.workspace_id``.  Optionally filtered
        by ``subject_key`` and/or ``field_key``.
        """
        stmt = (
            select(ClaimVersion)
            .join(Claim, ClaimVersion.claim_id == Claim.id)
            .where(
                Claim.workspace_id == ctx.workspace_id,
                ClaimVersion.visibility_status == "eligible",
            )
        )
        if subject_key is not None:
            stmt = stmt.where(Claim.subject_key == subject_key)
        if field_key is not None:
            stmt = stmt.where(Claim.field_key == field_key)

        return list(self._session.scalars(stmt).all())

    # ------------------------------------------------------------------
    # Generation operations
    # ------------------------------------------------------------------

    def create_candidate_generation(
        self,
        ctx: WorkspaceContext,
        version_ids: list[str],
    ) -> MemoryGeneration:
        """Build a new candidate generation from a list of version IDs.

        All versions must belong to claims owned by ``ctx.workspace_id``.
        Raises ``CrossWorkspaceError`` if any version belongs to a different
        workspace.

        Parameters
        ----------
        ctx:
            Resolved workspace context.
        version_ids:
            Explicit list of ``ClaimVersion.id`` values to include.

        Returns
        -------
        MemoryGeneration
            The new candidate generation (not yet active).
        """
        # Validate that every version belongs to this workspace.
        for vid in version_ids:
            version = self._session.get(ClaimVersion, vid)
            if version is None:
                raise ValueError(f"ClaimVersion '{vid}' not found.")

            claim = self._session.get(Claim, version.claim_id)
            if claim is None or claim.workspace_id != ctx.workspace_id:
                raise CrossWorkspaceError(
                    f"ClaimVersion '{vid}' belongs to a different workspace."
                )

        workspace = self._session.get(MemoryWorkspace, ctx.workspace_id)
        if workspace is None:
            raise WorkspaceNotFoundError(f"Workspace '{ctx.workspace_id}' not found.")

        generation = MemoryGeneration(
            workspace_id=ctx.workspace_id,
            state="candidate",
            base_revision=workspace.revision,
        )
        self._session.add(generation)
        self._session.flush()

        for vid in version_ids:
            version = self._session.get(ClaimVersion, vid)
            assert version is not None  # validated above
            self._session.add(
                GenerationClaimVersion(
                    generation_id=generation.id,
                    workspace_id=ctx.workspace_id,
                    claim_id=version.claim_id,
                    version_id=vid,
                )
            )

        self._session.flush()
        return generation

    def activate_generation(
        self,
        ctx: WorkspaceContext,
        generation_id: str,
        source_trust: TrustLevel,
        authorized_approval: bool = False,
        sandbox_mode: bool = False,
    ) -> MemoryWorkspace:
        """Atomically stage activation of a current candidate.

        The caller owns the Session transaction and must commit or
        roll back the entire operation. No commit occurs here.
        """
        decision = self._policy.evaluate(
            MemoryPolicyContext(
                operation=Operation.ACTIVATE,
                source_trust=source_trust,
                authorized_approval=authorized_approval,
                sandbox_mode=sandbox_mode,
            )
        )
        if not decision.allowed:
            raise PolicyDeniedError(decision.reason)

        # Lock and refresh the workspace before reading its revision.
        ws = self._session.scalar(
            select(MemoryWorkspace)
            .where(MemoryWorkspace.id == ctx.workspace_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if ws is None or ws.workspace_key != ctx.workspace_key:
            raise WorkspaceNotFoundError(
                "Workspace context does not match the database."
            )

        generation = self._session.get(
            MemoryGeneration,
            generation_id,
            populate_existing=True,
        )
        if generation is None:
            raise ValueError("Candidate generation not found.")

        if generation.workspace_id != ws.id:
            raise CrossWorkspaceError("Candidate belongs to another workspace.")

        if generation.state != "candidate":
            raise ValueError("Only candidate generations can be activated.")

        if generation.base_revision is None:
            raise StaleWorkspaceError(
                "Candidate has no recorded base revision; rebuild it."
            )

        if generation.base_revision != ws.revision:
            raise StaleWorkspaceError(
                "Candidate is stale: "
                f"base revision {generation.base_revision}, "
                f"current revision {ws.revision}."
            )

        memberships = self._session.scalars(
            select(GenerationClaimVersion).where(
                GenerationClaimVersion.generation_id == generation.id
            )
        ).all()

        for membership in memberships:
            version = self._session.get(
                ClaimVersion,
                membership.version_id,
                populate_existing=True,
            )
            if version is None:
                raise ValueError("Candidate references missing evidence.")

            if version.visibility_status != "eligible" or version.trust_status not in (
                "verified",
                "provisional",
            ):
                raise PolicyDeniedError(
                    "Candidate contains an ineligible claim version."
                )

            if version.trust_status == "provisional" and not sandbox_mode:
                raise PolicyDeniedError(
                    "Provisional memory requires isolated sandbox mode."
                )

            if (
                membership.workspace_id != ws.id
                or membership.claim_id != version.claim_id
            ):
                raise CrossWorkspaceError("Candidate membership ownership mismatch.")

        if ws.active_generation_id is not None:
            previous = self._session.get(MemoryGeneration, ws.active_generation_id)
            if previous is not None and previous.state == "active":
                previous.state = "retired"

        generation.state = "active"
        ws.active_generation_id = generation.id
        ws.revision += 1

        # Atomicity is finalized by the caller's transaction commit.
        self._session.flush()
        return ws

    def _lock_security_workspace(self, ctx: WorkspaceContext) -> MemoryWorkspace:
        ws = self._session.scalar(
            select(MemoryWorkspace)
            .where(MemoryWorkspace.id == ctx.workspace_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if ws is None or ws.workspace_key != ctx.workspace_key:
            raise WorkspaceNotFoundError("Invalid workspace context.")
        return ws

    def _record_security_change(
        self,
        ws: MemoryWorkspace,
        actor: AuthorizationContext,
        operation: str,
        target_id: str,
        old_status: str,
        new_status: str,
        reason: str,
    ) -> None:
        self._session.add(
            MemorySecurityAudit(
                workspace_id=ws.id,
                actor_id=actor.actor_id,
                actor_role=actor.role.value,
                operation=operation,
                target_id=target_id,
                old_status=old_status,
                new_status=new_status,
                reason=reason,
                policy_version=POLICY_VERSION,
            )
        )

    def _invalidate_active_generation(self, ws: MemoryWorkspace) -> None:
        if ws.active_generation_id is not None:
            previous = self._session.get(MemoryGeneration, ws.active_generation_id)
            if previous is not None and previous.state == "active":
                previous.state = "retired"
            ws.active_generation_id = None

    def set_claim_visibility(
        self,
        ctx: WorkspaceContext,
        version_id: str,
        status: str,
        actor: AuthorizationContext,
        reason: str,
    ) -> ClaimVersion:
        """Authorized quarantine or release of a claim version."""
        if status not in {"eligible", "quarantined"}:
            raise ValueError("Unsupported visibility transition.")
        if not reason.strip():
            raise ValueError("A review reason is required.")

        allowed_roles = (
            frozenset({ActorRole.REVIEWER})
            if status == "eligible"
            else frozenset(
                {
                    ActorRole.REVIEWER,
                    ActorRole.RECOVERY_SERVICE,
                }
            )
        )
        require_authorization(actor, ctx.workspace_id, allowed_roles)

        ws = self._lock_security_workspace(ctx)

        version = self._session.scalar(
            select(ClaimVersion)
            .join(Claim, Claim.id == ClaimVersion.claim_id)
            .where(
                ClaimVersion.id == version_id,
                Claim.workspace_id == ws.id,
            )
            .with_for_update(of=ClaimVersion)
            .execution_options(populate_existing=True)
        )
        if version is None:
            raise CrossWorkspaceError("Claim version is unavailable in this workspace.")

        old_status = version.visibility_status
        if old_status == status:
            raise ValueError("Claim version already has this status.")

        if status == "eligible":
            source = self._session.get(Source, version.source_id)
            if (
                version.trust_status != "verified"
                or source is None
                or source.trust_status != "verified"
                or old_status != "quarantined"
            ):
                raise PolicyDeniedError(
                    "Release requires verified source and claim evidence."
                )

        version.visibility_status = status

        if status == "quarantined":
            # Fail closed: retire active memory, which may depend
            # on this version. Future recovery rebuilds a candidate.
            self._invalidate_active_generation(ws)

        ws.revision += 1
        self._record_security_change(
            ws,
            actor,
            "set_claim_visibility",
            version.id,
            old_status,
            status,
            reason,
        )
        self._session.flush()
        return version

    def review_source_trust(
        self,
        ctx: WorkspaceContext,
        source_id: str,
        status: str,
        actor: AuthorizationContext,
        reason: str,
        evidence_reference: str,
    ) -> Source:
        """Reviewer-authorized source trust assessment.

        Source records are globally shared in the existing schema.
        Until sources are workspace-owned, a source referenced by
        multiple workspaces cannot be reviewed using this method.
        """
        if status not in {"verified", "disputed"}:
            raise ValueError("Unsupported source trust transition.")
        if not reason.strip() or not evidence_reference.strip():
            raise ValueError("Review reason and evidence reference are required.")

        require_authorization(
            actor,
            ctx.workspace_id,
            frozenset({ActorRole.REVIEWER}),
        )
        ws = self._lock_security_workspace(ctx)

        linked_workspace_ids = set(
            self._session.scalars(
                select(Claim.workspace_id)
                .join(
                    ClaimVersion,
                    ClaimVersion.claim_id == Claim.id,
                )
                .where(ClaimVersion.source_id == source_id)
                .distinct()
            ).all()
        )
        if linked_workspace_ids != {ws.id}:
            raise AuthorizationDeniedError(
                "Source must belong exclusively to this workspace."
            )

        source = self._session.scalar(
            select(Source)
            .where(Source.id == source_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if source is None:
            raise ValueError("Source not found.")

        old_status = source.trust_status
        if old_status == status:
            raise ValueError("Source already has this trust status.")

        source.trust_status = status

        if status == "disputed":
            versions = self._session.scalars(
                select(ClaimVersion)
                .where(ClaimVersion.source_id == source_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            ).all()
            for version in versions:
                version.visibility_status = "quarantined"
            self._invalidate_active_generation(ws)

        ws.revision += 1
        self._record_security_change(
            ws,
            actor,
            "review_source_trust",
            source.id,
            old_status,
            status,
            f"{reason}; evidence={evidence_reference}",
        )
        self._session.flush()
        return source
