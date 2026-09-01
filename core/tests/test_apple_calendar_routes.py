from cauco_core.connectors.models import (
    ConnectorRequest,
    PermissionDecision,
    PolicyEvaluation,
    RoutingResult,
)


def _routing(request: ConnectorRequest) -> RoutingResult:
    eligible = request.confirmation_request_id == request.request_id
    evaluation = PolicyEvaluation(
        PermissionDecision.ELIGIBLE if eligible else PermissionDecision.AWAITING_CONFIRMATION,
        "eligible" if eligible else "confirmation_mismatch",
        executable=eligible,
    )
    return RoutingResult(
        request.request_id,
        request.capability_id,
        "test.calendar",
        ("test.calendar",) if eligible else (),
        {} if eligible else {"test.calendar": evaluation.reason_code},
        {"test.calendar": evaluation},
        False,
        eligible,
        (),
    )


class CalendarRouteConnector:
    def list_calendars(self, limit: int):
        return {"results": [], "result_count": 0, "truncated": False}


def test_calendar_list_confirmation_is_propagated(client, monkeypatch):
    captured = []
    client.app.state.apple_calendar_connector = CalendarRouteConnector()

    def resolve(request):
        captured.append(request)
        return _routing(request)

    monkeypatch.setattr(client.app.state.connector_runtime, "resolve", resolve)

    base = {"request_id": "calendardebug003", "requester_id": "localuser"}
    assert client.get("/api/apple-calendar/calendars", params=base).status_code == 403
    assert client.get(
        "/api/apple-calendar/calendars",
        params={**base, "confirmation_request_id": "otherrequest"},
    ).status_code == 403
    response = client.get(
        "/api/apple-calendar/calendars",
        params={**base, "confirmation_request_id": base["request_id"]},
    )
    assert response.status_code == 200
    assert [item.confirmation_request_id for item in captured] == [None, "otherrequest", base["request_id"]]


def test_calendar_event_range_route_does_not_receive_calendar_list_confirmation(client, monkeypatch):
    captured = []

    def resolve(request):
        captured.append(request)
        return RoutingResult(
            request.request_id, request.capability_id, None, (), {}, {}, False, False, ()
        )

    monkeypatch.setattr(client.app.state.connector_runtime, "resolve", resolve)
    response = client.get(
        "/api/apple-calendar/events",
        params={
            "start": "2026-08-21T10:00:00+03:00",
            "end": "2026-08-21T11:00:00+03:00",
            "request_id": "calendarevents001",
            "requester_id": "localuser",
        },
    )
    assert response.status_code == 403
    assert captured[0].capability_id == "calendar.events.range"
    assert captured[0].confirmation_request_id is None
