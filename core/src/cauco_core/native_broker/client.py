from __future__ import annotations

import json
import os
import socket
from datetime import datetime, timezone
from typing import Any

MAX_REQUEST = 16 * 1024
MAX_RESPONSE = 32 * 1024


class NativeBrokerUnavailable(Exception):
    pass


class NativeBrokerClient:
    def __init__(self, socket_path: str | None = None, token: str | None = None, timeout: float = 1.0) -> None:
        self.socket_path = socket_path if socket_path is not None else os.environ.get("CAUCO_NATIVE_BROKER_SOCKET")
        self.token = token if token is not None else os.environ.get("CAUCO_NATIVE_BROKER_TOKEN")
        self.timeout = max(0.1, min(timeout, 3.0))

    @property
    def configured(self) -> bool:
        return bool(self.socket_path and self.token and self.socket_path.startswith("/"))

    def contacts_status(self) -> dict[str, Any]:
        request = {
            "protocolVersion": "native-capability-broker-v1", "requestId": "core-native-status",
            "capability": "contacts.status", "requesterId": "core", "origin": "localCore",
            "explicitUserRequest": False, "requestLocale": "en", "responseLocale": "en",
            "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "arguments": {},
        }
        return self.request(request)

    def request(self, request: dict[str, Any]) -> dict[str, Any]:
        if not self.configured:
            raise NativeBrokerUnavailable("native broker unavailable")
        envelope = json.dumps({"token": self.token, "request": request}, separators=(",", ":"), allow_nan=False).encode() + b"\n"
        if len(envelope) > MAX_REQUEST:
            raise NativeBrokerUnavailable("native broker request unavailable")
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(self.timeout)
                client.connect(self.socket_path)  # type: ignore[arg-type]
                client.sendall(envelope)
                data = bytearray()
                while len(data) <= MAX_RESPONSE:
                    chunk = client.recv(4096)
                    if not chunk:
                        break
                    data.extend(chunk)
                    if b"\n" in chunk:
                        break
                if len(data) > MAX_RESPONSE:
                    raise NativeBrokerUnavailable("native broker response unavailable")
                response = json.loads(bytes(data).split(b"\n", 1)[0])
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            raise NativeBrokerUnavailable("native broker unavailable") from error
        if not isinstance(response, dict) or response.get("protocolVersion") != "native-capability-broker-v1" or response.get("requestId") != request.get("requestId") or response.get("capability") != request.get("capability"):
            raise NativeBrokerUnavailable("native broker response invalid")
        if response.get("outcome") not in {"success", "rejected", "unavailable", "notImplemented", "failed"}:
            raise NativeBrokerUnavailable("native broker response invalid")
        return {"outcome": response["outcome"], "result": response.get("result"), "error": response.get("error"), "limitations": response.get("limitations", []), "method": response.get("method")}
