import sys
from cauco_core.connectors.models import (CapabilityDefinition, ConnectorAccessMode, ConnectorAvailability,
    ConnectorHealth, ConnectorIdentity, ConnectorPlatform, ConnectorRiskLevel)
from .native import BrokerCalendarGateway, UnavailableCalendarGateway
from .permissions import CALENDAR_PERMISSION_ID, permission_definition

class AppleCalendarConnector:
    def __init__(self, gateway=None, broker_client=None):
        self.gateway = (BrokerCalendarGateway(broker_client) if broker_client is not None and broker_client.configured
                        else (gateway or UnavailableCalendarGateway()))
        self._metadata = ConnectorIdentity("apple_calendar.local", "apple_calendar", "1.0",
            ConnectorAvailability.AVAILABLE if sys.platform == "darwin" and isinstance(self.gateway, BrokerCalendarGateway)
            else ConnectorAvailability.UNAVAILABLE, ConnectorHealth.UNKNOWN, ConnectorPlatform.MACOS, True,
            application_bundle_id="com.apple.iCal", name_message_key="apple_calendar.name",
            description_message_key="apple_calendar.description",
            capability_ids=("calendar.calendars.list", "calendar.events.range", "calendar.events.get"),
            limitations=("Read-only; calendar data is not read by the status endpoint.",))
    @property
    def metadata(self): return self._metadata
    def capabilities(self):
        return tuple(CapabilityDefinition(item, "calendar", item.split(".")[-1], "personal_data_read",
            ConnectorAccessMode.READ, ConnectorRiskLevel.MODERATE, exposes_personal_data=True,
            required_permission_ids=(CALENDAR_PERMISSION_ID,), name_message_key=f"{item}.name",
            description_message_key=f"{item}.description") for item in self.metadata.capability_ids)
    def permissions(self): return (permission_definition(self.gateway.authorization_state()),)
    def list_calendars(self, limit=50):
        return self.gateway.list(limit)
    def events_range(self, start, end, limit=100, calendar_reference=None):
        return self.gateway.events_range(start, end, limit, calendar_reference)
