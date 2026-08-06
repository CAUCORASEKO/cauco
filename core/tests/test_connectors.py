"""Focused tests for the metadata-only connector runtime."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from cauco_core.connectors import (
    CapabilityDefinition,
    ConnectorAccessMode,
    ConnectorAvailability,
    ConnectorHealth,
    ConnectorIdentity,
    ConnectorPermissionPolicy,
    ConnectorPlatform,
    ConnectorRegistry,
    ConnectorRequest,
    ConnectorRiskLevel,
    ConnectorRuntime,
    PermissionDefinition,
    PermissionState,
)
from cauco_core.connectors.exceptions import ConnectorNotFoundError, DuplicateConnectorError


class InertConnector:
    def __init__(self, connector_id: str, priority: int = 0, state=PermissionState.GRANTED):
        self.metadata = ConnectorIdentity(
            connector_id,
            "provider",
            "1.0",
            ConnectorAvailability.AVAILABLE,
            ConnectorHealth.HEALTHY,
            ConnectorPlatform.MACOS,
            True,
            priority=priority,
            capability_ids=("mail.search",),
        )
        self._capability = CapabilityDefinition(
            "mail.search",
            "mail",
            "search",
            "query",
            ConnectorAccessMode.READ,
            ConnectorRiskLevel.LOW,
            required_permission_ids=("mail.read",),
        )
        self._permissions = (PermissionDefinition("mail.read", "mail", state, "os", False, True),)

    def capabilities(self):
        return (self._capability,)

    def permissions(self):
        return self._permissions


def request(**changes):
    values = dict(
        request_id="request.one",
        capability_id="mail.search",
        preferred_connector_id=None,
        requester_id="agent.one",
        request_locale="es-CL",
        response_locale="es",
        interface_locale="fi-FI",
        fallback_locale="en",
        arguments={"nested": [1, {"ok": True}]},
        explicit_user_request=True,
        created_at=datetime.now(UTC),
        confirmation_request_id=None,
    )
    values.update(changes)
    return ConnectorRequest(**values)


def test_models_are_frozen_and_deeply_immutable():
    model = request()
    with pytest.raises(FrozenInstanceError):
        model.request_id = "other"  # type: ignore[misc]
    with pytest.raises(TypeError):
        model.arguments["nested"] = ()  # type: ignore[index]
    with pytest.raises(TypeError):
        model.arguments["nested"][1]["ok"] = False  # type: ignore[index]


@pytest.mark.parametrize("value", [b"x", {"x"}, float("nan"), float("inf"), object()])
def test_arguments_reject_non_json_values(value):
    with pytest.raises(ValueError):
        request(arguments={"value": value})


def test_locale_and_timestamp_validation():
    with pytest.raises(ValueError):
        request(request_locale="de")
    with pytest.raises(ValueError):
        request(created_at=datetime.now())


def test_capability_contradictions_are_rejected():
    with pytest.raises(ValueError):
        CapabilityDefinition(
            "mail.write",
            "mail",
            "write",
            "mutation",
            ConnectorAccessMode.READ,
            ConnectorRiskLevel.LOW,
            mutates_external_state=True,
        )
    with pytest.raises(ValueError):
        CapabilityDefinition(
            "mail.delete",
            "mail",
            "delete",
            "mutation",
            ConnectorAccessMode.DELETE,
            ConnectorRiskLevel.HIGH,
            mutates_external_state=False,
        )


def test_registry_is_deterministic_and_typed():
    registry = ConnectorRegistry()
    registry.register(InertConnector("zeta"))
    registry.register(InertConnector("alpha"))
    assert [item.connector_id for item in registry.list()] == ["alpha", "zeta"]
    assert registry.discover("mail.search")[0].connector_id == "alpha"
    with pytest.raises(DuplicateConnectorError):
        registry.register(InertConnector("alpha"))
    with pytest.raises(ConnectorNotFoundError):
        registry.get_metadata("missing")
    with pytest.raises(ValueError):
        registry.list(101)


def test_policy_requires_permission_and_confirmation():
    connector = InertConnector("alpha")
    policy = ConnectorPermissionPolicy()
    result = policy.evaluate(connector.metadata, connector.capabilities()[0], (), request())
    assert result.reason_code == "permission_missing"
    delete = CapabilityDefinition(
        "mail.delete",
        "mail",
        "delete",
        "mutation",
        ConnectorAccessMode.DELETE,
        ConnectorRiskLevel.HIGH,
        confirmation_required=True,
        mutates_external_state=True,
    )
    granted = connector.permissions()
    result = policy.evaluate(
        connector.metadata, delete, granted, request(capability_id="mail.delete")
    )
    assert result.reason_code == "confirmation_required"


def test_runtime_prefers_priority_and_never_executes():
    registry = ConnectorRegistry()
    registry.register(InertConnector("low", priority=1))
    registry.register(InertConnector("high", priority=5))
    result = ConnectorRuntime(registry, ConnectorPermissionPolicy()).resolve(
        request(preferred_connector_id="low")
    )
    assert result.selected_connector_id == "low"
    fallback = ConnectorRuntime(registry, ConnectorPermissionPolicy()).resolve(
        request(preferred_connector_id="missing")
    )
    assert fallback.selected_connector_id == "high"
    assert result.method == "connector-routing-v1"
    assert result.limitations
