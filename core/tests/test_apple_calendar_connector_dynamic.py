from cauco_core.connectors.apple_calendar.connector import AppleCalendarConnector
from cauco_core.native_broker import NativeBrokerUnavailable
from cauco_core.connectors.models import ConnectorAvailability, PermissionState


class ToggleBroker:
    def __init__(self, configured=False, state="granted"):
        self.configured = configured
        self.state = state
        self.status_calls = 0

    def calendar_status(self):
        self.status_calls += 1
        if self.state == "fail":
            raise NativeBrokerUnavailable("broker unavailable")
        return {"result": {"state": self.state}}


def test_calendar_broker_configuration_is_dynamic_and_fail_closed(monkeypatch):
    monkeypatch.setattr("cauco_core.connectors.apple_calendar.connector.sys.platform", "darwin")
    broker = ToggleBroker()
    connector = AppleCalendarConnector(broker_client=broker)
    assert connector.metadata.availability == ConnectorAvailability.UNAVAILABLE
    assert connector.permissions()[0].state == PermissionState.UNAVAILABLE
    assert broker.status_calls == 0

    broker.configured = True
    assert connector.metadata.availability == ConnectorAvailability.AVAILABLE
    assert connector.permissions()[0].state == PermissionState.GRANTED
    assert broker.status_calls == 1

    broker.state = "fail"
    assert connector.permissions()[0].state == PermissionState.UNAVAILABLE
    assert broker.status_calls == 2


def test_calendar_dynamic_gateway_never_synthesizes_granted(monkeypatch):
    monkeypatch.setattr("cauco_core.connectors.apple_calendar.connector.sys.platform", "darwin")
    broker = ToggleBroker(configured=True, state="unavailable")
    connector = AppleCalendarConnector(broker_client=broker)
    assert connector.permissions()[0].state == PermissionState.UNAVAILABLE
    assert connector.permissions()[0].state != PermissionState.GRANTED
