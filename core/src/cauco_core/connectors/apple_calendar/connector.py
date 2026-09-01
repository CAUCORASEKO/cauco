import sys
from threading import Lock
from cauco_core.connectors.models import (CapabilityDefinition, ConnectorAccessMode, ConnectorAvailability,
    ConnectorHealth, ConnectorIdentity, ConnectorPlatform, ConnectorRiskLevel)
from .native import DynamicBrokerCalendarGateway, UnavailableCalendarGateway
from .permissions import CALENDAR_PERMISSION_ID, permission_definition

class AppleCalendarConnector:
    def __init__(self, gateway=None, broker_client=None):
        self._broker_client = broker_client
        self.gateway = (DynamicBrokerCalendarGateway(broker_client) if broker_client is not None
                        else (gateway or UnavailableCalendarGateway()))
        self._gateway_is_dynamic = broker_client is not None
        self._metadata = ConnectorIdentity("apple_calendar.local", "apple_calendar", "1.0",
            ConnectorAvailability.UNAVAILABLE, ConnectorHealth.UNKNOWN, ConnectorPlatform.MACOS, True,
            application_bundle_id="com.apple.iCal", name_message_key="apple_calendar.name",
            description_message_key="apple_calendar.description",
            capability_ids=("calendar.calendars.list", "calendar.events.range", "calendar.events.get", "calendar.events.create"),
            limitations=("Status reads no calendar data.", "Event creation requires an explicit confirmed request; no background writes.",))
        self._create_lock = Lock(); self._created = {}
    @property
    def metadata(self):
        if not self._gateway_is_dynamic:
            return self._metadata
        availability = (ConnectorAvailability.AVAILABLE
                         if sys.platform == "darwin" and self._broker_client.configured
                         else ConnectorAvailability.UNAVAILABLE)
        return ConnectorIdentity(
            self._metadata.connector_id, self._metadata.provider_id, self._metadata.version,
            availability, self._metadata.health, self._metadata.platform, self._metadata.local,
            priority=self._metadata.priority, application_bundle_id=self._metadata.application_bundle_id,
            name_message_key=self._metadata.name_message_key,
            description_message_key=self._metadata.description_message_key,
            capability_ids=self._metadata.capability_ids, limitations=self._metadata.limitations,
            diagnostics=self._metadata.diagnostics)
    def capabilities(self):
        definitions = []
        for item in self.metadata.capability_ids:
            create = item == "calendar.events.create"
            definitions.append(CapabilityDefinition(item, "calendar", item.split(".")[-1], "mutation" if create else "personal_data_read",
                ConnectorAccessMode.WRITE if create else ConnectorAccessMode.READ, ConnectorRiskLevel.MODERATE,
                confirmation_required=create, mutates_external_state=create, exposes_personal_data=True,
                required_permission_ids=(CALENDAR_PERMISSION_ID,), name_message_key=f"{item}.name",
                description_message_key=f"{item}.description"))
        return tuple(definitions)
    def permissions(self): return (permission_definition(self.gateway.authorization_state()),)
    def list_calendars(self, limit=50):
        return self.gateway.list(limit)
    def events_range(self, start, end, limit=100, calendar_reference=None):
        return self.gateway.events_range(start, end, limit, calendar_reference)
    def get_event(self, reference):
        return self.gateway.event_get(reference)
    def create_event(self, request_id, **kwargs):
        with self._create_lock:
            if request_id in self._created: return self._created[request_id]
            result = self.gateway.event_create(**kwargs); self._created[request_id] = result
            if len(self._created) > 200: self._created.pop(next(iter(self._created)))
            return result
