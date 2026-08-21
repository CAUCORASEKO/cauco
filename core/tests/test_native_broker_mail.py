import pytest

from cauco_core.native_broker import (
    NativeBrokerClient,
    NativeBrokerReferenceNotFound,
    NativeBrokerUnavailable,
)


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


def valid_accounts_response() -> dict:
    return {
        "outcome": "success",
        "result": {
            "results": [
                {
                    "account_reference": "mailacct_0123456789abcdef",
                    "name": "Personal",
                    "email_addresses": ["user@example.com"],
                }
            ],
            "result_count": 1,
            "truncated": False,
        },
        "error": None,
        "limitations": ["maximum 20 accounts", "opaque account references"],
        "method": "mail.accounts.list.v1",
    }


def valid_mailboxes_response() -> dict:
    return {
        "outcome": "success",
        "result": {
            "results": [
                {
                    "mailbox_reference": "mailbox_0123456789abcdef",
                    "name": "Inbox",
                }
            ],
            "result_count": 1,
            "truncated": False,
        },
        "error": None,
        "limitations": ["maximum 100 mailboxes", "opaque mailbox references"],
        "method": "mail.mailboxes.list.v1",
    }


def test_mail_accounts_list_builds_exact_request_and_accepts_bounded_metadata() -> None:
    client, calls = client_with_response(valid_accounts_response())

    response = client.mail_accounts_list()

    assert response["result"]["result_count"] == 1
    assert calls[0]["capability"] == "mail.accounts.list"
    assert calls[0]["arguments"] == {}
    assert calls[0]["explicitUserRequest"] is True


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("account_reference", "native-account-id"),
        ("name", "x" * 301),
        ("name", "bad\nname"),
        ("email_addresses", ["x" * 321]),
        ("email_addresses", ["bad\naddress"]),
        ("email_addresses", ["user@example.com"] * 21),
    ],
)
def test_mail_accounts_list_rejects_malformed_or_unbounded_fields(
    field: str, value: object
) -> None:
    response = valid_accounts_response()
    response["result"]["results"][0][field] = value
    client, _ = client_with_response(response)

    with pytest.raises(NativeBrokerUnavailable):
        client.mail_accounts_list()


@pytest.mark.parametrize("extra", ["id", "native_identifier", "account_id"])
def test_mail_accounts_list_rejects_native_or_extra_identifiers(extra: str) -> None:
    response = valid_accounts_response()
    response["result"]["results"][0][extra] = "secret"
    client, _ = client_with_response(response)

    with pytest.raises(NativeBrokerUnavailable):
        client.mail_accounts_list()


def test_mail_accounts_list_rejects_more_than_twenty_rows() -> None:
    response = valid_accounts_response()
    row = dict(response["result"]["results"][0])
    response["result"]["results"] = [dict(row) for _ in range(21)]
    response["result"]["result_count"] = 21
    client, _ = client_with_response(response)

    with pytest.raises(NativeBrokerUnavailable):
        client.mail_accounts_list()


def test_mail_mailboxes_list_builds_exact_opaque_reference_request() -> None:
    client, calls = client_with_response(valid_mailboxes_response())

    response = client.mail_mailboxes_list("mailacct_0123456789abcdef")

    assert response["result"]["result_count"] == 1
    assert calls[0]["capability"] == "mail.mailboxes.list"
    assert calls[0]["arguments"] == {
        "account_reference": "mailacct_0123456789abcdef"
    }


@pytest.mark.parametrize("reference", ["", "native-id", "mailacct_short", 1, None])
def test_mail_mailboxes_list_rejects_invalid_account_references(reference: object) -> None:
    client, calls = client_with_response(valid_mailboxes_response())

    with pytest.raises(ValueError):
        client.mail_mailboxes_list(reference)  # type: ignore[arg-type]

    assert calls == []


def test_mail_mailboxes_list_maps_unknown_or_stale_account_reference() -> None:
    response = {
        "outcome": "rejected",
        "result": None,
        "error": {"code": "mail_account_reference_unknown"},
    }
    client, _ = client_with_response(response)

    with pytest.raises(NativeBrokerReferenceNotFound):
        client.mail_mailboxes_list("mailacct_0123456789abcdef")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("mailbox_reference", "native-mailbox-id"),
        ("name", "x" * 301),
        ("name", "bad\x00name"),
    ],
)
def test_mail_mailboxes_list_rejects_malformed_fields(
    field: str, value: object
) -> None:
    response = valid_mailboxes_response()
    response["result"]["results"][0][field] = value
    client, _ = client_with_response(response)

    with pytest.raises(NativeBrokerUnavailable):
        client.mail_mailboxes_list("mailacct_0123456789abcdef")


@pytest.mark.parametrize("extra", ["id", "native_identifier", "mailbox_id"])
def test_mail_mailboxes_list_rejects_native_or_extra_identifiers(extra: str) -> None:
    response = valid_mailboxes_response()
    response["result"]["results"][0][extra] = "secret"
    client, _ = client_with_response(response)

    with pytest.raises(NativeBrokerUnavailable):
        client.mail_mailboxes_list("mailacct_0123456789abcdef")


def test_mail_mailboxes_list_rejects_more_than_one_hundred_rows() -> None:
    response = valid_mailboxes_response()
    row = dict(response["result"]["results"][0])
    response["result"]["results"] = [dict(row) for _ in range(101)]
    response["result"]["result_count"] = 101
    client, _ = client_with_response(response)

    with pytest.raises(NativeBrokerUnavailable):
        client.mail_mailboxes_list("mailacct_0123456789abcdef")


@pytest.mark.parametrize("kind", ["account", "mailbox"])
def test_mail_account_and_mailbox_lists_reject_invalid_result_envelopes(kind: str) -> None:
    response = valid_accounts_response() if kind == "account" else valid_mailboxes_response()
    response["result"]["result_count"] = 2
    client, _ = client_with_response(response)

    with pytest.raises(NativeBrokerUnavailable):
        if kind == "account":
            client.mail_accounts_list()
        else:
            client.mail_mailboxes_list("mailacct_0123456789abcdef")


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
