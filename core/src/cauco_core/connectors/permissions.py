"""Fail-closed, deterministic connector permission policy."""

from .models import (
    CapabilityDefinition,
    ConnectorAccessMode,
    ConnectorAvailability,
    ConnectorIdentity,
    ConnectorRequest,
    ConnectorRiskLevel,
    PermissionDecision,
    PermissionDefinition,
    PermissionState,
    PolicyEvaluation,
)


class ConnectorPermissionPolicy:
    def evaluate(
        self,
        connector: ConnectorIdentity,
        capability: CapabilityDefinition | None,
        permissions: tuple[PermissionDefinition, ...],
        request: ConnectorRequest,
    ) -> PolicyEvaluation:
        if capability is None:
            return PolicyEvaluation(PermissionDecision.UNAVAILABLE, "capability_metadata_invalid")
        if connector.availability not in (
            ConnectorAvailability.AVAILABLE,
            ConnectorAvailability.DEGRADED,
        ):
            return PolicyEvaluation(PermissionDecision.UNAVAILABLE, "connector_unavailable")
        permission_map = {item.permission_id: item for item in permissions}
        required = capability.required_permission_ids
        missing = tuple(item for item in required if item not in permission_map)
        if missing:
            return PolicyEvaluation(
                PermissionDecision.AWAITING_PERMISSION,
                "permission_missing",
                missing_permission_ids=missing,
            )
        denied = tuple(
            item
            for item in required
            if permission_map[item].state
            in (PermissionState.DENIED, PermissionState.RESTRICTED, PermissionState.UNAVAILABLE)
        )
        if denied:
            state = permission_map[denied[0]].state
            reason = {
                PermissionState.RESTRICTED: "permission_restricted",
                PermissionState.UNAVAILABLE: "permission_unavailable",
            }.get(state, "permission_denied")
            return PolicyEvaluation(
                PermissionDecision.DENIED,
                reason,
                denied_permission_ids=denied,
            )
        pending = tuple(
            item
            for item in required
            if permission_map[item].state
            in (PermissionState.UNKNOWN, PermissionState.NOT_REQUESTED, PermissionState.PENDING)
        )
        if pending:
            return PolicyEvaluation(
                PermissionDecision.AWAITING_PERMISSION,
                "permission_pending",
                missing_permission_ids=pending,
            )
        confirmation = (
            capability.confirmation_required
            or capability.mutates_external_state
            or capability.access_mode
            in (ConnectorAccessMode.DELETE, ConnectorAccessMode.EXTERNAL_SEND)
            or capability.risk_level in (ConnectorRiskLevel.HIGH, ConnectorRiskLevel.CRITICAL)
        )
        if confirmation and request.confirmation_request_id != request.request_id:
            reason = (
                "confirmation_mismatch"
                if request.confirmation_request_id
                else "confirmation_required"
            )
            return PolicyEvaluation(
                PermissionDecision.AWAITING_CONFIRMATION,
                reason,
                confirmation_required=True,
            )
        return PolicyEvaluation(
            PermissionDecision.ELIGIBLE,
            "eligible",
            confirmation_required=confirmation,
            executable=True,
        )


PermissionPolicy = ConnectorPermissionPolicy
