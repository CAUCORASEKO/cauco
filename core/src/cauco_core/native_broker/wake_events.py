from __future__ import annotations

import json
import os
import socket
import threading
import queue
from datetime import datetime
from typing import Any

ALLOWED = {"type", "event_reference", "phrase_key", "detected_at", "confidence"}

def validate_event(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != ALLOWED or value.get("type") != "wakeword.detected":
        raise ValueError("invalid wake event")
    if value["phrase_key"] != "hola_cauco" or not isinstance(value["event_reference"], str) or not 1 <= len(value["event_reference"]) <= 100:
        raise ValueError("invalid wake event")
    try: datetime.fromisoformat(value["detected_at"].replace("Z", "+00:00"))
    except (TypeError, ValueError): raise ValueError("invalid wake event")
    confidence = value["confidence"]
    if confidence is not None and (not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1):
        raise ValueError("invalid wake event")
    return {k: value[k] for k in ALLOWED if k != "type"}

class WakeWordEventService:
    def __init__(self, socket_path: str | None = None):
        self.socket_path = socket_path or os.environ.get("CAUCO_WAKE_EVENT_SOCKET")
        self._subscribers: set[queue.Queue[dict[str, Any]]] = set()
        self._lock = threading.Lock()
        self._server: socket.socket | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self.socket_path or not self.socket_path.startswith("/"): return
        if self._server is not None: return
        if len(self.socket_path.encode()) >= 104: return
        try:
            os.unlink(self.socket_path)
        except FileNotFoundError: pass
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(self.socket_path); os.chmod(self.socket_path, 0o600); self._server.listen(2)
        self._thread = threading.Thread(target=self._accept, daemon=True); self._thread.start()

    def stop(self) -> None:
        if self._server: self._server.close(); self._server = None
        if self.socket_path:
            try: os.unlink(self.socket_path)
            except FileNotFoundError: pass

    def subscribe(self):
        q: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
        with self._lock: self._subscribers.add(q)
        return q, lambda: self._subscribers.discard(q)

    def publish(self, value: Any) -> None:
        try: event = validate_event(value)
        except ValueError: return
        with self._lock:
            for q in tuple(self._subscribers):
                try: q.put_nowait(event)
                except queue.Full: pass

    def _accept(self) -> None:
        while self._server:
            try: conn, _ = self._server.accept()
            except OSError: return
            with conn:
                try:
                    line = conn.recv(4096).split(b"\n", 1)[0]
                    self.publish(json.loads(line))
                except (OSError, ValueError, json.JSONDecodeError): pass
