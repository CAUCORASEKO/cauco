from fastapi.testclient import TestClient


class FakeWakeClient:
    configured = True

    def __init__(self, outcome="success", result=None):
        self.calls = []
        self.outcome = outcome
        self.result = result or {"available": True, "state": "listening", "active": True, "accepted": True}

    def _call(self, name, *args):
        self.calls.append((name, args))
        return {"outcome": self.outcome, "result": self.result}

    def wakeword_status(self): return self._call("wakeword.status")
    def wakeword_start(self, phrase_key, locale): return self._call("wakeword.start", phrase_key, locale)
    def wakeword_stop(self): return self._call("wakeword.stop")


def test_wakeword_routes_are_bounded_and_forward_explicit_request(client: TestClient):
    fake = FakeWakeClient()
    client.app.state.native_broker_client = fake
    assert client.get("/api/native/wakeword/status").status_code == 200
    response = client.post("/api/native/wakeword/start", json={"phrase_key": "hola_cauco", "locale": "es-ES"})
    assert response.json()["active"] is True
    assert fake.calls == [("wakeword.status", ()), ("wakeword.start", ("hola_cauco", "es-ES"))]


def test_wakeword_http_rejects_unsupported_fields_before_native(client: TestClient):
    fake = FakeWakeClient()
    client.app.state.native_broker_client = fake
    for body in ({"phrase_key": "other", "locale": "es-ES"}, {"phrase_key": "hola_cauco", "locale": "bad"}, {"phrase_key": "hola_cauco", "locale": "es-ES", "explicitUserRequest": False}, {"phrase_key": "hola_cauco", "locale": "es-ES", "model_path": "/tmp/x"}):
        assert client.post("/api/native/wakeword/start", json=body).status_code == 422
    assert fake.calls == []


def test_wakeword_unavailable_and_stop_are_safe(client: TestClient):
    fake = FakeWakeClient(outcome="unavailable")
    client.app.state.native_broker_client = fake
    assert client.get("/api/native/wakeword/status").json() == {"available": False, "state": "unavailable", "active": False}
    assert client.post("/api/native/wakeword/stop").json() == {"available": False, "state": "unavailable", "active": False}
    assert fake.calls == [("wakeword.status", ()), ("wakeword.stop", ())]
