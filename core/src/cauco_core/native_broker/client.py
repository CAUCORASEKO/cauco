from __future__ import annotations

import json
import os
import re
import socket
from datetime import timedelta
from datetime import datetime, timezone
from typing import Any

MAX_REQUEST = 16 * 1024
MAX_RESPONSE = 32 * 1024
BROKER_REF = re.compile(r"^contact_[A-Za-z0-9_-]{8,80}$")
CALENDAR_REF = re.compile(r"^calendar_[A-Za-z0-9_-]{8,80}$")


class NativeBrokerUnavailable(Exception):
    pass

class NativeBrokerReferenceNotFound(Exception):
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

    def calendar_status(self) -> dict[str, Any]:
        request = {
            "protocolVersion": "native-capability-broker-v1", "requestId": "core-native-calendar-status",
            "capability": "calendar.status", "requesterId": "core", "origin": "localCore",
            "explicitUserRequest": False, "requestLocale": "en", "responseLocale": "en",
            "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "arguments": {},
        }
        response = self.request(request)
        result = response.get("result")
        valid_states = {"notRequested", "restricted", "denied", "granted", "unavailable"}
        if (response.get("outcome") != "success" or not isinstance(result, dict)
                or result.get("permissionId") != "macos.calendar.read"
                or result.get("state") not in valid_states
                or not isinstance(result.get("available"), bool)):
            raise NativeBrokerUnavailable("native calendar status invalid")
        return response

    def calendar_list(self, limit: int = 50) -> dict[str, Any]:
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 50:
            raise ValueError("Invalid calendar list limit")
        request = {"protocolVersion": "native-capability-broker-v1", "requestId": "core-native-calendar-list",
            "capability": "calendar.calendars.list", "requesterId": "core", "origin": "localCore",
            "explicitUserRequest": True, "requestLocale": "en", "responseLocale": "en",
            "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "arguments": {"limit": limit}}
        response = self.request(request); result = response.get("result")
        if response.get("outcome") != "success" or not isinstance(result, dict): raise NativeBrokerUnavailable("native calendar list rejected")
        rows = result.get("results")
        if not isinstance(rows, list) or len(rows) > 50 or result.get("result_count") != len(rows) or not isinstance(result.get("truncated"), bool):
            raise NativeBrokerUnavailable("native calendar list response invalid")
        allowed = {"calendar_reference", "title", "source_title", "type", "allows_content_modifications"}
        for row in rows:
            if not isinstance(row, dict) or set(row) != allowed or any(k in row for k in ("calendarIdentifier", "sourceIdentifier", "identifier", "native_identifier")):
                raise NativeBrokerUnavailable("native calendar list response invalid")
            if not isinstance(row["calendar_reference"], str) or not CALENDAR_REF.fullmatch(row["calendar_reference"]): raise NativeBrokerUnavailable("native calendar list response invalid")
            if any(not isinstance(row[k], str) or len(row[k]) > 200 or any(ord(c) < 32 for c in row[k]) for k in ("title", "source_title", "type")) or not isinstance(row["allows_content_modifications"], bool):
                raise NativeBrokerUnavailable("native calendar list response invalid")
        return response

    def calendar_events_range(self, start: str, end: str, limit: int = 100, calendar_reference: str | None = None) -> dict[str, Any]:
        if not isinstance(start, str) or not isinstance(end, str) or not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100 or (calendar_reference is not None and not isinstance(calendar_reference, str)):
            raise ValueError("Invalid calendar event range arguments")
        try:
            start_date = datetime.fromisoformat(start.replace("Z", "+00:00"))
            end_date = datetime.fromisoformat(end.replace("Z", "+00:00"))
        except (TypeError, ValueError) as error:
            raise ValueError("Invalid calendar event range dates") from error
        if start_date.tzinfo is None or end_date.tzinfo is None or start_date >= end_date or end_date - start_date > timedelta(days=31):
            raise ValueError("Invalid calendar event range dates")
        args = {"start": start, "end": end, "limit": limit};
        if calendar_reference is not None: args["calendar_reference"] = calendar_reference
        request = {"protocolVersion":"native-capability-broker-v1","requestId":"core-native-calendar-events-range","capability":"calendar.events.range","requesterId":"core","origin":"localCore","explicitUserRequest":True,"requestLocale":"en","responseLocale":"en","createdAt":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),"arguments":args}
        response = self.request(request); result = response.get("result")
        if response.get("outcome") != "success" or not isinstance(result, dict) or not isinstance(result.get("results"), list) or len(result["results"]) > 100 or result.get("result_count") != len(result["results"]) or not isinstance(result.get("truncated"), bool) or not isinstance(result.get("range_start"), str) or not isinstance(result.get("range_end"), str): raise NativeBrokerUnavailable("native calendar event range invalid")
        allowed = {"event_reference","calendar_reference","title","start","end","all_day","location","notes"}
        for row in result["results"]:
            if not isinstance(row, dict) or set(row) != allowed or any(k in row for k in ("eventIdentifier","event_identifier","calendarIdentifier","native_identifier")): raise NativeBrokerUnavailable("native calendar event range invalid")
            if not re.fullmatch(r"^event_[A-Za-z0-9_-]{8,80}$", row["event_reference"]) or not re.fullmatch(r"^calendar_[A-Za-z0-9_-]{8,80}$", row["calendar_reference"]): raise NativeBrokerUnavailable("native calendar event range invalid")
            if any(not isinstance(row[k], str) or len(row[k]) > n for k,n in (("title",300),("location",300),("notes",1000),("start",100),("end",100))) or not isinstance(row["all_day"], bool): raise NativeBrokerUnavailable("native calendar event range invalid")
        return response

    def calendar_event_get(self, event_reference: str) -> dict[str, Any]:
        if not isinstance(event_reference, str) or not re.fullmatch(r"^event_[A-Za-z0-9_-]{8,80}$", event_reference): raise ValueError("Invalid event reference")
        request = {"protocolVersion":"native-capability-broker-v1","requestId":"core-native-calendar-event-get","capability":"calendar.events.get","requesterId":"core","origin":"localCore","explicitUserRequest":True,"requestLocale":"en","responseLocale":"en","createdAt":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),"arguments":{"event_reference":event_reference}}
        response = self.request(request); result = response.get("result")
        allowed = {"event_reference","calendar_reference","title","start","end","all_day","location","notes"}
        if response.get("outcome") != "success":
            if isinstance(response.get("error"), dict) and response["error"].get("code") == "event_reference_unknown": raise NativeBrokerReferenceNotFound("calendar event reference not found")
            raise NativeBrokerUnavailable("native calendar event get rejected")
        if not isinstance(result, dict) or set(result) != allowed or result.get("event_reference") != event_reference or any(k in result for k in ("eventIdentifier","event_identifier","calendarIdentifier","native_identifier")): raise NativeBrokerUnavailable("native calendar event get invalid")
        if not isinstance(result.get("calendar_reference"), str) or not CALENDAR_REF.fullmatch(result["calendar_reference"]): raise NativeBrokerUnavailable("native calendar event get invalid")
        if any(not isinstance(result[k], str) or len(result[k]) > n for k,n in (("title",300),("location",300),("notes",1000),("start",100),("end",100))) or not isinstance(result.get("all_day"), bool): raise NativeBrokerUnavailable("native calendar event get invalid")
        try: starts = datetime.fromisoformat(result["start"].replace("Z", "+00:00")); ends = datetime.fromisoformat(result["end"].replace("Z", "+00:00"))
        except ValueError as error: raise NativeBrokerUnavailable("native calendar event get invalid") from error
        if starts.tzinfo is None or ends.tzinfo is None or ends < starts: raise NativeBrokerUnavailable("native calendar event get invalid")
        return response

    def calendar_event_create(self, title, start, end, all_day, calendar_reference=None, location=None, notes=None):
        if not isinstance(title, str) or not title or len(title)>300 or not isinstance(start,str) or not isinstance(end,str) or not isinstance(all_day,bool) or (location is not None and (not isinstance(location,str) or len(location)>300)) or (notes is not None and (not isinstance(notes,str) or len(notes)>1000)): raise ValueError("Invalid calendar event create arguments")
        if calendar_reference is not None and (not isinstance(calendar_reference,str) or not CALENDAR_REF.fullmatch(calendar_reference)): raise ValueError("Invalid calendar reference")
        try: sd=datetime.fromisoformat(start.replace("Z","+00:00")); ed=datetime.fromisoformat(end.replace("Z","+00:00"))
        except ValueError as error: raise ValueError("Invalid event dates") from error
        if sd.tzinfo is None or ed.tzinfo is None or sd >= ed: raise ValueError("Invalid event dates")
        args={"title":title,"start":start,"end":end,"all_day":all_day};
        for key,value in (("calendar_reference",calendar_reference),("location",location),("notes",notes)):
            if value is not None: args[key]=value
        request={"protocolVersion":"native-capability-broker-v1","requestId":"core-native-calendar-event-create","capability":"calendar.events.create","requesterId":"core","origin":"localCore","explicitUserRequest":True,"requestLocale":"en","responseLocale":"en","createdAt":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),"arguments":args}
        response=self.request(request); result=response.get("result"); allowed={"event_reference","calendar_reference","title","start","end","all_day","location","notes"}
        if response.get("outcome")!="success" or not isinstance(result,dict) or set(result)!=allowed: raise NativeBrokerUnavailable("native calendar event create failed")
        if not re.fullmatch(r"^event_[A-Za-z0-9_-]{8,80}$",result["event_reference"]) or not CALENDAR_REF.fullmatch(result["calendar_reference"]): raise NativeBrokerUnavailable("native calendar event create invalid")
        if result["title"]!=title or result["all_day"]!=all_day or result["start"] is None or result["end"] is None: raise NativeBrokerUnavailable("native calendar event create invalid")
        return response

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
