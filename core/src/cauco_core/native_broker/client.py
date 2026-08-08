from __future__ import annotations

import json
import os
import re
import socket
from datetime import datetime, timezone
from typing import Any

MAX_REQUEST = 16 * 1024
MAX_RESPONSE = 32 * 1024
BROKER_REF = re.compile(r"^contact_[A-Za-z0-9_-]{8,80}$")


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

    def contacts_search(self, query: str, limit: int = 20) -> dict[str, Any]:
        if not isinstance(query, str) or not query.strip() or len(query) > 200 or not 1 <= limit <= 20:
            raise ValueError("Invalid contacts search arguments")
        request = {"protocolVersion": "native-capability-broker-v1", "requestId": "core-native-search",
            "capability": "contacts.search", "requesterId": "core", "origin": "localCore",
            "explicitUserRequest": True, "requestLocale": "en", "responseLocale": "en",
            "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "arguments": {"query": query, "limit": limit}}
        response = self.request(request)
        if response["outcome"] != "success" or not isinstance(response.get("result"), dict):
            raise NativeBrokerUnavailable("native contacts search rejected")
        result = response["result"]
        if not isinstance(result.get("results"), list) or not isinstance(result.get("result_count"), (int, float)) or not isinstance(result.get("truncated"), bool) or len(result["results"]) > 20:
            raise NativeBrokerUnavailable("native contacts response invalid")
        for item in result["results"]:
            if not isinstance(item, dict) or any(key in item for key in ("identifier", "native_identifier")):
                raise NativeBrokerUnavailable("native contacts response invalid")
            if not isinstance(item.get("contact_reference"), str) or not BROKER_REF.fullmatch(item["contact_reference"]):
                raise NativeBrokerUnavailable("native contacts response invalid")
            for field in ("display_name", "given_name", "family_name", "organization"):
                if not isinstance(item.get(field, ""), str) or len(item[field]) > 200:
                    raise NativeBrokerUnavailable("native contacts response invalid")
            for field, max_items in (("emails", 10), ("phones", 10)):
                if not isinstance(item.get(field), list) or len(item[field]) > max_items:
                    raise NativeBrokerUnavailable("native contacts response invalid")
        return response

    def contacts_get(self, contact_reference: str) -> dict[str, Any]:
        if not isinstance(contact_reference, str) or not re.fullmatch(r"contact_[A-Za-z0-9_-]{8,80}", contact_reference):
            raise ValueError("Invalid contact reference")
        request = {"protocolVersion": "native-capability-broker-v1", "requestId": "core-native-get",
            "capability": "contacts.get", "requesterId": "core", "origin": "localCore",
            "explicitUserRequest": True, "requestLocale": "en", "responseLocale": "en",
            "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "arguments": {"contactRef": contact_reference}}
        response = self.request(request)
        if response["outcome"] != "success" or not isinstance(response.get("result"), dict):
            raise NativeBrokerUnavailable("native contacts get rejected")
        result = response["result"]
        if result.get("contact_reference") != contact_reference or "identifier" in result or "native_identifier" in result:
            raise NativeBrokerUnavailable("native contacts get response invalid")
        return response

    def contacts_list_limited(self, limit: int = 20) -> dict[str, Any]:
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 20:
            raise ValueError("Invalid contacts list limit")
        request = {"protocolVersion": "native-capability-broker-v1", "requestId": "core-native-list",
            "capability": "contacts.list_limited", "requesterId": "core", "origin": "localCore",
            "explicitUserRequest": True, "requestLocale": "en", "responseLocale": "en",
            "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "arguments": {"limit": limit}}
        response = self.request(request)
        result = response.get("result")
        if response["outcome"] != "success" or not isinstance(result, dict):
            raise NativeBrokerUnavailable("native contacts list rejected")
        results = result.get("results")
        if not isinstance(results, list) or len(results) > 20 or result.get("result_count") != len(results) or not isinstance(result.get("truncated"), bool):
            raise NativeBrokerUnavailable("native contacts list response invalid")
        for item in results:
            if not isinstance(item, dict) or "identifier" in item or "native_identifier" in item:
                raise NativeBrokerUnavailable("native contacts list response invalid")
            if not isinstance(item.get("contact_reference"), str) or not BROKER_REF.fullmatch(item["contact_reference"]):
                raise NativeBrokerUnavailable("native contacts list response invalid")
        return response

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
