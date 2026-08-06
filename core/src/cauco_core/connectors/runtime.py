"""Read-only deterministic connector routing."""

from types import MappingProxyType

from .models import ConnectorRequest, PermissionDecision, PolicyEvaluation, RoutingResult


class ConnectorRuntime:
    def __init__(self, registry, policy) -> None:
        self.registry = registry
        self.policy = policy

    def resolve(self, request: ConnectorRequest) -> RoutingResult:
        candidates = self.registry.discover(request.capability_id, availability=None)
        eligible: list[str] = []
        rejected: dict[str, str] = {}
        evaluations: dict[str, PolicyEvaluation] = {}
        for metadata in candidates:
            connector = self.registry._get_connector(metadata.connector_id)
            capability = next(
                (
                    item
                    for item in connector.capabilities()
                    if item.capability_id == request.capability_id
                ),
                None,
            )
            evaluation = self.policy.evaluate(
                metadata, capability, connector.permissions(), request
            )
            evaluations[metadata.connector_id] = evaluation
            if evaluation.decision == PermissionDecision.ELIGIBLE:
                eligible.append(metadata.connector_id)
            else:
                rejected[metadata.connector_id] = evaluation.reason_code
        eligible.sort(
            key=lambda connector_id: (
                -self.registry.get_metadata(connector_id).priority,
                connector_id,
            )
        )
        selected = (
            request.preferred_connector_id if request.preferred_connector_id in eligible else None
        )
        if selected is None and eligible:
            selected = eligible[0]
        confirmation = bool(selected and evaluations[selected].confirmation_required)
        return RoutingResult(
            request_id=request.request_id,
            capability_id=request.capability_id,
            selected_connector_id=selected,
            eligible_connector_ids=tuple(eligible),
            rejected_connector_reason_codes=rejected,
            policy_evaluations=MappingProxyType(dict(evaluations)),
            confirmation_required=confirmation,
            executable=selected is not None,
            limitations=("Resolution is observational; no connector action is executed.",),
        )
