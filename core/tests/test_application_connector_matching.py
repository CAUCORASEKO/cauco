"""Focused tests for observational connector matching."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from cauco_core.application_connector_matching import (
    ApplicationConnectorMatchingService,
    ApplicationConnectorResolver,
    MatchStatus,
    ProviderMapping,
    ProviderMappingRegistry,
)
from cauco_core.application_inventory.models import (
    ApplicationAvailability,
    ApplicationBundleSnapshot,
    ApplicationSource,
)
from cauco_core.connectors.models import (
    ConnectorAvailability,
    ConnectorHealth,
    ConnectorIdentity,
    ConnectorPlatform,
)
from cauco_core.connectors.registry import ConnectorRegistry


class Connector:
    def __init__(
        self,
        connector_id="mail.connector",
        bundle_id="com.apple.mail",
        availability=ConnectorAvailability.AVAILABLE,
    ):
        self.metadata = ConnectorIdentity(
            connector_id,
            "apple_mail",
            "1",
            availability,
            ConnectorHealth.HEALTHY,
            ConnectorPlatform.MACOS,
            True,
            application_bundle_id=bundle_id,
        )

    def capabilities(self):
        return ()

    def permissions(self):
        return ()


def app(bundle_id="com.apple.mail", name="Mail"):
    return ApplicationBundleSnapshot(
        "app_mail",
        name,
        "mail",
        bundle_id,
        "/Applications/Mail.app",
        "Mail.app",
        None,
        None,
        None,
        ApplicationSource.SYSTEM_APPLICATIONS,
        ApplicationAvailability.AVAILABLE,
        discovered_at=datetime.now(UTC),
    )


def test_mapping_registry_is_exact_and_deterministic():
    registry = ProviderMappingRegistry(
        (
            ProviderMapping("z_provider", ("com.z.App",)),
            ProviderMapping("a_provider", ("com.a.App",)),
        )
    )
    assert [item.provider_id for item in registry.list()] == ["a_provider", "z_provider"]
    assert registry.find("com.a.App").provider_id == "a_provider"
    assert registry.find("com.a.Other") is None
    with pytest.raises(ValueError):
        registry.register(ProviderMapping("other", ("com.a.App",)))


def test_resolver_matches_registered_connector_without_policy_or_routing():
    connectors = ConnectorRegistry()
    connectors.register(Connector())
    result = ApplicationConnectorResolver(ProviderMappingRegistry(), connectors).resolve(app())
    assert result.status == MatchStatus.MATCHED_REGISTERED_CONNECTOR
    assert not result.permissions_evaluated
    assert not result.routing_evaluated
    with pytest.raises(FrozenInstanceError):
        result.status = MatchStatus.NO_MATCH  # type: ignore[misc]


def test_resolver_distinguishes_known_provider_and_missing_metadata():
    resolver = ApplicationConnectorResolver(ProviderMappingRegistry(), ConnectorRegistry())
    assert resolver.resolve(app()).status == MatchStatus.MATCHED_KNOWN_PROVIDER
    assert resolver.resolve(app(None)).status == MatchStatus.UNAVAILABLE_METADATA


def test_service_refresh_is_explicit_and_filters():
    class Inventory:
        def __init__(self):
            self.items = (app(),)

        def list(self, limit=100):
            return self.items

    connectors = ConnectorRegistry()
    service = ApplicationConnectorMatchingService(
        Inventory(), ApplicationConnectorResolver(ProviderMappingRegistry(), connectors)
    )
    assert service.list() == ()
    service.refresh()
    assert service.list(status=MatchStatus.MATCHED_KNOWN_PROVIDER)[0].inventory_id == "app_mail"
    assert service.summary().inventory_count == 1
