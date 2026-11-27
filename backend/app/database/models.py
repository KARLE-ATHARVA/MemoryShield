import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# MemoryWorkspace — defined first so other tables can reference it.
# ---------------------------------------------------------------------------


class MemoryWorkspace(Base):
    __tablename__ = "memory_workspaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_key: Mapped[str] = mapped_column(String(100), unique=True)
    # active_generation_id is enforced by a composite FK (active_generation_id, id)
    # → memory_generations(id, workspace_id), which guarantees that the activated
    # generation belongs to this workspace.  The simple ForeignKey annotation is
    # intentionally absent here; the constraint lives in __table_args__ below.
    active_generation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    # Relationships
    claims: Mapped[list["Claim"]] = relationship(back_populates="workspace")
    generations: Mapped[list["MemoryGeneration"]] = relationship(
        back_populates="workspace",
        foreign_keys="MemoryGeneration.workspace_id",
    )

    __table_args__ = (
        # Composite FK ensures the active generation belongs to THIS workspace.
        # Requires uq_generation_id_workspace on memory_generations.
        ForeignKeyConstraint(
            ["active_generation_id", "id"],
            ["memory_generations.id", "memory_generations.workspace_id"],
            name="fk_workspace_active_generation_owned",
            use_alter=True,
        ),
    )


# ---------------------------------------------------------------------------
# Source — workspace-independent; a source document is a global evidence
# record that individual workspaces may reference via ClaimVersion.
# ---------------------------------------------------------------------------


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str | None] = mapped_column(
        ForeignKey("memory_workspaces.id"), nullable=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    source_type: Mapped[str] = mapped_column(String(50))
    sha256: Mapped[str] = mapped_column(String(64))
    trust_status: Mapped[str] = mapped_column(String(30), default="unverified")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "sha256",
            name="uq_source_workspace_sha256",
        ),
        CheckConstraint(
            "trust_status IN ('unverified', 'provisional', 'verified', 'disputed')",
            name="ck_source_trust",
        ),
    )


# ---------------------------------------------------------------------------
# Claim — workspace-scoped.
# A claim represents the identity (subject + field) of a persistent fact.
# The same (subject_key, field_key) pair may exist independently in
# different workspaces; they are unrelated records.
# ---------------------------------------------------------------------------


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("memory_workspaces.id"), nullable=False
    )
    subject_key: Mapped[str] = mapped_column(String(150))
    field_key: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    workspace: Mapped["MemoryWorkspace"] = relationship(back_populates="claims")

    __table_args__ = (
        # Uniqueness is now scoped to the workspace — the same (subject, field)
        # pair in two different workspaces produces two independent claims.
        UniqueConstraint(
            "workspace_id",
            "subject_key",
            "field_key",
            name="uq_claim_identity",
        ),
        # Required by the composite FK on generation_claim_versions so that
        # (claim_id, workspace_id) can be verified as a unique pair.
        UniqueConstraint(
            "id",
            "workspace_id",
            name="uq_claim_id_workspace",
        ),
    )


# ---------------------------------------------------------------------------
# ClaimVersion — immutable value record for a Claim.
# ---------------------------------------------------------------------------


class ClaimVersion(Base):
    __tablename__ = "claim_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.id"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer)
    value: Mapped[str] = mapped_column(Text)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), nullable=False)
    trust_status: Mapped[str] = mapped_column(String(30), default="unverified")
    visibility_status: Mapped[str] = mapped_column(String(30), default="eligible")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    __table_args__ = (
        UniqueConstraint(
            "claim_id",
            "version_number",
            name="uq_claim_version_number",
        ),
        UniqueConstraint(
            "id",
            "claim_id",
            name="uq_version_claim_pair",
        ),
        CheckConstraint(
            "version_number >= 1",
            name="ck_version_positive",
        ),
        CheckConstraint(
            "trust_status IN ('unverified', 'provisional', 'verified', 'disputed')",
            name="ck_claim_version_trust",
        ),
        CheckConstraint(
            "visibility_status IN ('eligible', 'quarantined', 'superseded')",
            name="ck_claim_version_visibility",
        ),
    )


# ---------------------------------------------------------------------------
# MemoryArtifact — derived memory (e.g. AI-generated summaries).
# ---------------------------------------------------------------------------


class MemoryArtifact(Base):
    __tablename__ = "memory_artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    artifact_type: Mapped[str] = mapped_column(String(50))
    content: Mapped[str] = mapped_column(Text)
    visibility_status: Mapped[str] = mapped_column(String(30), default="eligible")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    __table_args__ = (
        CheckConstraint(
            "visibility_status IN ('eligible', 'quarantined', 'superseded')",
            name="ck_artifact_visibility",
        ),
    )


# ---------------------------------------------------------------------------
# DependencyEdge — provenance graph edge.
# ---------------------------------------------------------------------------


class DependencyEdge(Base):
    __tablename__ = "dependency_edges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    parent_type: Mapped[str] = mapped_column(String(50))
    parent_id: Mapped[str] = mapped_column(String(36))
    child_type: Mapped[str] = mapped_column(String(50))
    child_id: Mapped[str] = mapped_column(String(36))
    relationship_type: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    __table_args__ = (
        UniqueConstraint(
            "parent_type",
            "parent_id",
            "child_type",
            "child_id",
            "relationship_type",
            name="uq_dependency_edge",
        ),
        CheckConstraint(
            "NOT (parent_type = child_type AND parent_id = child_id)",
            name="ck_no_self_dependency",
        ),
        Index("ix_dependency_parent", "parent_type", "parent_id"),
        Index("ix_dependency_child", "child_type", "child_id"),
    )


# ---------------------------------------------------------------------------
# RetrievalEvent — records what versions were returned during a retrieval.
# ---------------------------------------------------------------------------


class RetrievalEvent(Base):
    __tablename__ = "retrieval_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(String(100))
    query: Mapped[str] = mapped_column(Text)
    retrieved_version_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


# ---------------------------------------------------------------------------
# AgentDecision — records an agent output linked to a retrieval event.
# ---------------------------------------------------------------------------


class AgentDecision(Base):
    __tablename__ = "agent_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(String(100))
    retrieval_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("retrieval_events.id"), nullable=True
    )
    output: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


# ---------------------------------------------------------------------------
# MemoryGeneration — a versioned snapshot of active memory claims.
# Each generation is owned by exactly one workspace.
# ---------------------------------------------------------------------------


class MemoryGeneration(Base):
    __tablename__ = "memory_generations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("memory_workspaces.id"), nullable=False
    )
    state: Mapped[str] = mapped_column(String(30), default="candidate")
    base_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    workspace: Mapped["MemoryWorkspace"] = relationship(
        back_populates="generations",
        foreign_keys=[workspace_id],
    )

    __table_args__ = (
        CheckConstraint(
            "base_revision IS NULL OR base_revision >= 0",
            name="ck_generation_base_revision_nonnegative",
        ),
        CheckConstraint(
            "state IN ('candidate', 'active', 'retired')",
            name="ck_generation_state",
        ),
        # Required by composite FKs on generation_claim_versions and
        # memory_workspaces so that workspace ownership can be enforced
        # declaratively at the database level.
        UniqueConstraint(
            "id",
            "workspace_id",
            name="uq_generation_id_workspace",
        ),
    )


# ---------------------------------------------------------------------------
# GenerationClaimVersion — membership table linking a generation to the
# specific claim version it includes.
#
# The composite FK (version_id, claim_id) → claim_versions(id, claim_id)
# prevents a generation from referencing a version that belongs to a
# different claim.  Workspace-level isolation is enforced by the application
# gateway which ensures generation.workspace_id == claim.workspace_id before
# inserting rows here.
# ---------------------------------------------------------------------------


class GenerationClaimVersion(Base):
    __tablename__ = "generation_claim_versions"

    generation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    claim_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # workspace_id is a redundant denormalized column required so that composite
    # FKs can enforce that the generation and claim share the same workspace
    # entirely within the database — without needing a trigger.
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False)
    version_id: Mapped[str] = mapped_column(String(36), nullable=False)

    __table_args__ = (
        # Original constraint: version must belong to the stated claim.
        ForeignKeyConstraint(
            ["version_id", "claim_id"],
            ["claim_versions.id", "claim_versions.claim_id"],
            name="fk_generation_correct_claim",
        ),
        # DB-level proof that the generation belongs to workspace_id.
        # Requires uq_generation_id_workspace on memory_generations.
        ForeignKeyConstraint(
            ["generation_id", "workspace_id"],
            ["memory_generations.id", "memory_generations.workspace_id"],
            name="fk_gcv_generation_workspace",
        ),
        # DB-level proof that the claim belongs to workspace_id.
        # Requires uq_claim_id_workspace on claims.
        ForeignKeyConstraint(
            ["claim_id", "workspace_id"],
            ["claims.id", "claims.workspace_id"],
            name="fk_gcv_claim_workspace",
        ),
    )


# ---------------------------------------------------------------------------
# Incident — workspace-scoped forensic incident.
# ---------------------------------------------------------------------------


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("memory_workspaces.id"), nullable=False
    )
    suspect_node_type: Mapped[str] = mapped_column(String(50))
    suspect_node_id: Mapped[str] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(30), default="open")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'investigating', "
            "'recovering', 'resolved', 'unresolved')",
            name="ck_incident_status",
        ),
    )


# ---------------------------------------------------------------------------
# RecoveryJob — workspace-scoped recovery operation.
# ---------------------------------------------------------------------------


class RecoveryJob(Base):
    __tablename__ = "recovery_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), nullable=False)
    candidate_generation_id: Mapped[str | None] = mapped_column(
        ForeignKey("memory_generations.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(30), default="planned")
    plan: Mapped[dict] = mapped_column(JSON, default=dict)
    verification_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('planned', 'approved', 'executing', "
            "'verifying', 'completed', 'failed')",
            name="ck_recovery_job_status",
        ),
    )


class MemorySecurityAudit(Base):
    """Append-only record of completed privileged memory operations."""

    __tablename__ = "memory_security_audit"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("memory_workspaces.id"), nullable=False
    )
    actor_id: Mapped[str] = mapped_column(String(150))
    actor_role: Mapped[str] = mapped_column(String(40))
    operation: Mapped[str] = mapped_column(String(60))
    target_id: Mapped[str] = mapped_column(String(36))
    old_status: Mapped[str] = mapped_column(String(40))
    new_status: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(Text)
    policy_version: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
