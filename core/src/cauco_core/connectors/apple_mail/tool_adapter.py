import json
from dataclasses import asdict
from datetime import UTC, datetime
from time import monotonic
from typing import Any

from cauco_agents import (
    EmailDraftInput,
    EmailListAccountsInput,
    EmailListMailboxesInput,
    EmailListMessagesInput,
)
from cauco_tools import ToolExecutionError, ToolExecutionRequest, ToolExecutionResult

from cauco_core.native_broker import (
    NativeBrokerReferenceNotFound,
    NativeBrokerUnavailable,
)
from cauco_core.native_broker.client import MAX_REQUEST


class EmailToolRuntimeAdapter:
    tool_id = "email"
    operations = frozenset({"list_accounts", "list_mailboxes", "list_messages", "draft"})

    def __init__(self, broker_client: Any) -> None:
        self.broker_client = broker_client

    def preflight(self, request: ToolExecutionRequest) -> dict[str, object]:
        if request.tool_id != self.tool_id or request.operation_id not in self.operations:
            raise ToolExecutionError("invalid_request", "Email operation is invalid.")

        arguments = dict(request.arguments)

        try:
            read_inputs = {
                "list_accounts": EmailListAccountsInput,
                "list_mailboxes": EmailListMailboxesInput,
                "list_messages": EmailListMessagesInput,
            }
            if request.operation_id in read_inputs:
                value = read_inputs[request.operation_id](**arguments)
                return asdict(value)

            arguments.pop("request_id", None)
            value = EmailDraftInput(**arguments)
        except (TypeError, ValueError) as error:
            raise ToolExecutionError(
                "invalid_arguments",
                "Email arguments are invalid.",
            ) from error

        normalized = asdict(value)
        self._validate_transport_size(normalized)

        return normalized

    def _validate_transport_size(self, arguments: dict[str, object]) -> None:
        token = getattr(self.broker_client, "token", None)
        if not isinstance(token, str) or not token:
            return

        probe = {
            "token": token,
            "request": {
                "protocolVersion": "native-capability-broker-v1",
                "requestId": "email_draft_" + ("0" * 24),
                "capability": "mail.draft.create",
                "requesterId": "core",
                "origin": "localCore",
                "explicitUserRequest": True,
                "requestLocale": "en",
                "responseLocale": "en",
                "createdAt": "2026-01-01T00:00:00.000000Z",
                "arguments": arguments,
            },
        }

        encoded = (
            json.dumps(
                probe,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
            + b"\n"
        )

        if len(encoded) > MAX_REQUEST:
            raise ToolExecutionError(
                "request_too_large",
                "Email draft content is too large for the native broker transport.",
            )

    def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        started_at = datetime.now(tz=UTC)
        started = monotonic()

        arguments = self.preflight(request)

        if request.operation_id != "draft":
            return self._execute_read(request, arguments, started_at, started)

        request_id = request.arguments.get("request_id")
        if not isinstance(request_id, str) or not request_id.startswith("email_draft_"):
            raise ToolExecutionError(
                "invalid_arguments",
                "Email draft mutation request ID is invalid.",
            )

        try:
            response = self.broker_client.request(
                {
                    "protocolVersion": "native-capability-broker-v1",
                    "requestId": request_id,
                    "capability": "mail.draft.create",
                    "requesterId": "core",
                    "origin": "localCore",
                    "explicitUserRequest": True,
                    "requestLocale": "en",
                    "responseLocale": "en",
                    "createdAt": started_at.isoformat().replace("+00:00", "Z"),
                    "arguments": arguments,
                }
            )
        except NativeBrokerUnavailable as error:
            raise ToolExecutionError(
                "email_unavailable",
                "Email draft creation is unavailable.",
            ) from error

        if response.get("outcome") != "success":
            raise ToolExecutionError(
                "email_draft_failed",
                "Email draft creation failed.",
            )

        result = response.get("result")
        if not isinstance(result, dict) or result.get("draft_created") is not True:
            raise ToolExecutionError(
                "invalid_response",
                "Email draft creation returned an invalid response.",
            )

        structured = {
            "recipient": arguments["recipient"],
            "subject": arguments["subject"],
            "draft_created": True,
            "verification_passed": True,
        }

        completed_at = datetime.now(tz=UTC)

        return ToolExecutionResult(
            tool_id=self.tool_id,
            operation_id=request.operation_id,
            success=True,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=max(0, round((monotonic() - started) * 1000)),
            output="Email draft created.",
            structured_data=structured,
            truncated=False,
            execution_performed=True,
            mutation_performed=True,
        )

    def _execute_read(
        self,
        request: ToolExecutionRequest,
        arguments: dict[str, object],
        started_at: datetime,
        started: float,
    ) -> ToolExecutionResult:
        try:
            if request.operation_id == "list_accounts":
                response = self.broker_client.mail_accounts_list()
                result_key = "accounts"
            elif request.operation_id == "list_mailboxes":
                response = self.broker_client.mail_mailboxes_list(
                    account_reference=arguments["account_reference"]
                )
                result_key = "mailboxes"
            else:
                response = self.broker_client.mail_messages_list(
                    mailbox_reference=arguments["mailbox_reference"],
                    limit=arguments["limit"],
                )
                result_key = "messages"
        except NativeBrokerReferenceNotFound as error:
            raise ToolExecutionError(
                "email_reference_not_found",
                "The Email account or mailbox reference is no longer available.",
            ) from error
        except NativeBrokerUnavailable as error:
            raise ToolExecutionError(
                "email_unavailable",
                "Email metadata listing is unavailable.",
            ) from error

        result = response.get("result")
        if not isinstance(result, dict):
            raise ToolExecutionError(
                "invalid_response",
                "Email metadata listing returned an invalid response.",
            )

        try:
            structured = {
                result_key: tuple(result["results"]),
                "result_count": result["result_count"],
                "truncated": result["truncated"],
            }
        except (KeyError, TypeError) as error:
            raise ToolExecutionError(
                "invalid_response",
                "Email metadata listing returned an invalid response.",
            ) from error

        output = json.dumps(structured, ensure_ascii=False, separators=(",", ":"))
        truncated = len(output) > request.max_output_chars

        return ToolExecutionResult(
            tool_id=self.tool_id,
            operation_id=request.operation_id,
            success=True,
            started_at=started_at,
            completed_at=datetime.now(tz=UTC),
            duration_ms=max(0, round((monotonic() - started) * 1000)),
            output=output[: request.max_output_chars],
            structured_data=structured,
            truncated=truncated,
            execution_performed=True,
            mutation_performed=False,
        )
