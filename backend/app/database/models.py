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
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(UTC)


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    filename: Mapped[str] = mapped_column(String(255))
    source_type: Mapped[str] = mapped_column(String(50))
    sha256: Mapped[str] = mapped_column(String(64))
    trust_status: Mapped[str] = mapped_column(String(30), default="unverified")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    __table_args__ = (
        CheckConstraint(
            "trust_status IN ('unverified', 'provisional', 'verified', 'disputed')",
            name="ck_source_trust",
        ),
    )


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    subject_key: Mapped[str] = mapped_column(String(150))
    field_key: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    __table_args__ = (
        UniqueConstraint("subject_key", "field_key", name="uq_claim_identity"),
    )


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


class RetrievalEvent(Base):
    __tablename__ = "retrieval_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(String(100))
    query: Mapped[str] = mapped_column(Text)
    retrieved_version_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


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


class MemoryGeneration(Base):
    __tablename__ = "memory_generations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    state: Mapped[str] = mapped_column(String(30), default="candidate")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    __table_args__ = (
        CheckConstraint(
            "state IN ('candidate', 'active', 'retired')",
            name="ck_generation_state",
        ),
    )


class GenerationClaimVersion(Base):
    __tablename__ = "generation_claim_versions"

    generation_id: Mapped[str] = mapped_column(
        ForeignKey("memory_generations.id"), primary_key=True
    )
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.id"), primary_key=True)
    version_id: Mapped[str] = mapped_column(String(36), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["version_id", "claim_id"],
            ["claim_versions.id", "claim_versions.claim_id"],
            name="fk_generation_correct_claim",
        ),
    )


class MemoryWorkspace(Base):
    __tablename__ = "memory_workspaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_key: Mapped[str] = mapped_column(String(100), unique=True)
    active_generation_id: Mapped[str | None] = mapped_column(
        ForeignKey("memory_generations.id"), nullable=True
    )
    revision: Mapped[int] = mapped_column(Integer, default=0)


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
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
