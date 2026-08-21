import pytest

from cauco_core.native_broker import NativeBrokerClient, NativeBrokerUnavailable


def client_with_response(response: dict) -> tuple[NativeBrokerClient, list[dict]]:
    client = NativeBrokerClient()
    calls: list[dict] = []

    def request(payload: dict) -> dict:
        calls.append(payload)
        return response

    client.request = request  # type: ignore[method-assign]
    return client, calls


def valid_response() -> dict:
    return {
        "outcome": "success",
        "result": {
            "results": [
                {
                    "message_reference": "mailmsg_0123456789abcdef",
                    "sender": "Sender <sender@example.com>",
                    "subject": "Subject",
                    "date_received": "2026-08-21T05:00:00.000Z",
                    "read": False,
                }
            ],
            "result_count": 1,
            "truncated": False,
        },
        "error": None,
        "limitations": [
            "Inbox only",
            "metadata only",
            "limit 1..20",
            "opaque message references",
            "no body or attachments",
        ],
        "method": "mail.messages.list.v1",
    }


def test_mail_messages_list_builds_bounded_native_request() -> None:
    client, calls = client_with_response(valid_response())

    response = client.mail_messages_list(limit=5)

    assert response["result"]["result_count"] == 1
    assert len(calls) == 1

    request = calls[0]

    assert request["capability"] == "mail.messages.list"
    assert request["requesterId"] == "core"
    assert request["origin"] == "localCore"
    assert request["explicitUserRequest"] is True
    assert request["arguments"] == {"limit": 5}


@pytest.mark.parametrize("limit", [0, 21, -1, True, 1.5, "5"])
def test_mail_messages_list_rejects_invalid_limits(limit: object) -> None:
    client, calls = client_with_response(valid_response())

    with pytest.raises(ValueError):
        client.mail_messages_list(limit=limit)  # type: ignore[arg-type]

    assert calls == []


def test_mail_messages_list_accepts_only_exact_bounded_metadata() -> None:
    client, _ = client_with_response(valid_response())

    response = client.mail_messages_list()

    message = response["result"]["results"][0]

    assert message == {
        "message_reference": "mailmsg_0123456789abcdef",
        "sender": "Sender <sender@example.com>",
        "subject": "Subject",
        "date_received": "2026-08-21T05:00:00.000Z",
        "read": False,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("message_reference", "native-id"),
        ("message_reference", "mailmsg_short"),
        ("sender", "x" * 321),
        ("sender", "bad\nheader"),
        ("subject", "x" * 301),
        ("subject", "bad\x00subject"),
        ("date_received", "not-a-date"),
        ("date_received", "2026-08-21T05:00:00"),
        ("read", 1),
        ("read", "false"),
    ],
)
def test_mail_messages_list_rejects_malformed_message_fields(
    field: str,
    value: object,
) -> None:
    response = valid_response()
    response["result"]["results"][0][field] = value
    client, _ = client_with_response(response)

    with pytest.raises(NativeBrokerUnavailable):
        client.mail_messages_list()


@pytest.mark.parametrize(
    "extra_field",
    ["id", "message_id", "native_identifier", "body", "attachments"],
)
def test_mail_messages_list_rejects_forbidden_or_extra_fields(
    extra_field: str,
) -> None:
    response = valid_response()
    response["result"]["results"][0][extra_field] = "secret"
    client, _ = client_with_response(response)

    with pytest.raises(NativeBrokerUnavailable):
        client.mail_messages_list()


def test_mail_messages_list_rejects_inconsistent_result_count() -> None:
    response = valid_response()
    response["result"]["result_count"] = 2
    client, _ = client_with_response(response)

    with pytest.raises(NativeBrokerUnavailable):
        client.mail_messages_list()


def test_mail_messages_list_rejects_more_rows_than_requested_limit() -> None:
    response = valid_response()
    row = dict(response["result"]["results"][0])
    response["result"]["results"] = [dict(row), dict(row)]
    response["result"]["result_count"] = 2

    client, _ = client_with_response(response)

    with pytest.raises(NativeBrokerUnavailable):
        client.mail_messages_list(limit=1)


def test_mail_messages_list_rejects_unexpected_result_fields() -> None:
    response = valid_response()
    response["result"]["account"] = "secret-account"
    client, _ = client_with_response(response)

    with pytest.raises(NativeBrokerUnavailable):
        client.mail_messages_list()
