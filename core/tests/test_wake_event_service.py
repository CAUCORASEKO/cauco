import json
import socket
import time
import uuid

from cauco_core.native_broker.wake_events import WakeWordEventService, validate_event


def frame(reference="wakeevt_1", **extra):
    value = {"type": "wakeword.detected", "event_reference": reference, "phrase_key": "hola_cauco", "detected_at": "2026-08-28T10:00:00Z", "confidence": 0.5}
    value.update(extra)
    return value

def socket_path():
    return f"/private/tmp/cauco-wake-test-{uuid.uuid4().hex[:8]}.sock"


def test_valid_event_is_delivered_once_to_active_subscriber(tmp_path):
    path = socket_path(); service = WakeWordEventService(path); service.start()
    queue, close = service.subscribe()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(path); client.sendall((json.dumps(frame()) + "\n").encode())
        event = queue.get(timeout=1)
        assert event == {k: v for k, v in frame().items() if k != "type"}
        assert queue.empty()
    finally:
        close(); service.stop()


def test_invalid_frames_are_rejected_without_leaking_details(tmp_path):
    path = socket_path(); service = WakeWordEventService(path); service.start(); queue, close = service.subscribe()
    try:
        for value in [b"not-json\n", json.dumps(frame(type="other")).encode() + b"\n", json.dumps(frame(phrase_key="other")).encode() + b"\n", json.dumps(frame(confidence=-1)).encode() + b"\n", json.dumps(frame(confidence=2)).encode() + b"\n", json.dumps({**frame(), "secret": "do-not-leak"}).encode() + b"\n"]:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.connect(path); client.sendall(value)
        time.sleep(0.05)
        assert queue.empty()
    finally:
        close(); service.stop()


def test_validation_is_strict_and_disconnected_subscriber_gets_no_replay():
    valid = validate_event(frame())
    assert set(valid) == {"event_reference", "phrase_key", "detected_at", "confidence"}
    for value in [frame(confidence=float("nan")), frame(confidence=float("inf"))]:
        try: validate_event(value)
        except ValueError: pass
        else: raise AssertionError("non-finite confidence accepted")
    service = WakeWordEventService(); queue, close = service.subscribe(); close(); service.publish(frame())
    assert queue.empty()


def test_service_start_stop_is_idempotent_and_removes_socket(tmp_path):
    path = socket_path(); service = WakeWordEventService(path)
    service.start(); service.start(); assert __import__("os").path.exists(path)
    service.stop(); service.stop(); assert not __import__("os").path.exists(path)
