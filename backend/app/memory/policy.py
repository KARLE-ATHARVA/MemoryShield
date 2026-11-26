from dataclasses import dataclass
from enum import Enum


class TrustLevel(str, Enum):
    UNVERIFIED = "unverified"
    PROVISIONAL = "provisional"
    VERIFIED = "verified"
    DISPUTED = "disputed"


class Operation(str, Enum):
    INGEST = "ingest"
    ACTIVATE = "activate"
    RESTORE = "restore"


@dataclass(frozen=True)
class MemoryPolicyContext:
    operation: Operation
    source_trust: TrustLevel
    authorized_approval: bool = False
    sandbox_mode: bool = False


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str


class MemoryTrustPolicy:
    """Pure policy evaluator; no database or LLM dependencies."""

    def evaluate(self, ctx: MemoryPolicyContext) -> PolicyDecision:
        if ctx.operation == Operation.INGEST:
            return PolicyDecision(
                allowed=True,
                reason="Source may be recorded without becoming trusted.",
            )

        if ctx.source_trust == TrustLevel.DISPUTED:
            return PolicyDecision(
                allowed=False,
                reason="Disputed evidence cannot be activated or restored.",
            )

        if ctx.operation == Operation.RESTORE:
            if ctx.source_trust != TrustLevel.VERIFIED:
                return PolicyDecision(
                    allowed=False,
                    reason="Restoration requires verified evidence.",
                )

            if not ctx.authorized_approval:
                return PolicyDecision(
                    allowed=False,
                    reason="Restoration requires authorized approval.",
                )

            return PolicyDecision(
                allowed=True,
                reason="Verified evidence and approval are present.",
            )

        if ctx.operation == Operation.ACTIVATE:
            if ctx.source_trust == TrustLevel.VERIFIED:
                return PolicyDecision(
                    allowed=True,
                    reason="Verified evidence may be activated.",
                )

            if ctx.source_trust == TrustLevel.PROVISIONAL and ctx.sandbox_mode:
                return PolicyDecision(
                    allowed=True,
                    reason="Provisional activation permitted in sandbox.",
                )

            return PolicyDecision(
                allowed=False,
                reason="Activation requires verified evidence.",
            )

        return PolicyDecision(
            allowed=False,
            reason="Unsupported operation.",
        )
