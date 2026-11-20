"""FastmailClient falls back to api.fastmail.com when the session's apiUrl is unreachable."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from lunchsync_sg.fastmail import (
    FALLBACK_API_URL,
    EmailMessage,
    FastmailClient,
    clear_alert_label,
    settled_references,
)

SESSION = {
    "apiUrl": "https://dc.api.example.test/jmap/api/",
    "primaryAccounts": {"urn:ietf:params:jmap:mail": "acc1"},
}


def _ok() -> MagicMock:
    response = MagicMock()
    response.json.return_value = {"methodResponses": [["Core/echo", {}, "0"]]}
    return response


def _client(post_side_effect: list) -> tuple[FastmailClient, MagicMock]:
    with patch("lunchsync_sg.fastmail.requests.Session") as session_cls:
        http = session_cls.return_value
        http.headers = {}
        http.get.return_value.json.return_value = SESSION
        http.post.side_effect = post_side_effect
        return FastmailClient("token"), http


def test_uses_session_api_url_when_reachable() -> None:
    client, http = _client([_ok()])
    client._call([["Core/echo", {}, "0"]])
    assert http.post.call_args.args[0] == SESSION["apiUrl"]


def test_falls_back_and_stays_on_fallback() -> None:
    client, http = _client([requests.ConnectTimeout("down"), _ok(), _ok()])
    client._call([["Core/echo", {}, "0"]])
    client._call([["Core/echo", {}, "0"]])
    urls = [c.args[0] for c in http.post.call_args_list]
    assert urls == [SESSION["apiUrl"], FALLBACK_API_URL, FALLBACK_API_URL]


def test_raises_when_fallback_also_unreachable() -> None:
    client, _ = _client([requests.ConnectTimeout("down"), requests.ConnectTimeout("down")])
    with pytest.raises(requests.ConnectionError):
        client._call([["Core/echo", {}, "0"]])


MAILBOXES = {"methodResponses": [["Mailbox/get", {"list": [
    {"id": "inbox", "name": "Inbox", "role": "inbox"},
    {"id": "arch", "name": "Archive", "role": "archive"},
    {"id": "bank", "name": "Bank", "role": None},
]}, "m"]]}


def _json(body: dict) -> MagicMock:
    response = MagicMock()
    response.json.return_value = body
    return response


def _set_ok(not_updated: dict | None = None) -> MagicMock:
    return _json({"methodResponses": [["Email/set", {"notUpdated": not_updated}, "s"]]})


def _email(email_id: str, *mailboxes: str) -> EmailMessage:
    return EmailMessage(
        message_id=f"<{email_id}>", subject="", received_at="", html="",
        email_id=email_id, mailbox_ids=frozenset(mailboxes),
    )


def test_remove_label_moves_label_only_emails_to_archive() -> None:
    client, http = _client([_json(MAILBOXES), _set_ok()])
    emails = [_email("a", "bank"), _email("b", "bank", "inbox"), _email("c", "arch")]
    assert client.remove_label(emails, "bank") == 2
    update = http.post.call_args.kwargs["json"]["methodCalls"][0][1]["update"]
    assert update == {
        "a": {"mailboxIds/bank": None, "mailboxIds/arch": True},
        "b": {"mailboxIds/bank": None},
    }


def test_remove_label_dry_run_and_nothing_to_do_send_no_update() -> None:
    client, http = _client([_json(MAILBOXES), _json(MAILBOXES)])
    assert client.remove_label([_email("a", "bank")], "Bank", dry_run=True) == 1
    assert client.remove_label([_email("c", "arch")], "Bank") == 0
    assert all(c.kwargs["json"]["methodCalls"][0][0] == "Mailbox/get"
               for c in http.post.call_args_list)


def test_remove_label_fails_on_not_updated_or_missing_mailbox() -> None:
    client, _ = _client([_json(MAILBOXES), _set_ok({"a": {"type": "forbidden"}})])
    with pytest.raises(RuntimeError, match="forbidden"):
        client.remove_label([_email("a", "bank")], "Bank")
    client, _ = _client([_json(MAILBOXES)])
    with pytest.raises(RuntimeError, match="no Fastmail mailbox"):
        client.remove_label([_email("a", "bank")], "Receipts")


def test_clear_alert_label_reports_errors_instead_of_raising() -> None:
    client = MagicMock()
    client.remove_label.side_effect = RuntimeError("JMAP error: accountReadOnly")
    assert clear_alert_label(client, [], dry_run=False, log=lambda _: None) == [
        "removing the Bank label: JMAP error: accountReadOnly"
    ]


def test_settled_references() -> None:
    in_lm = {"live1", "charge_up", "rev_up"}
    assert settled_references(
        ["live1", "live2"],
        [("charge_never", "rev_never"), ("charge_up", "rev_up"), ("charge_up2", "rev_pending")],
        in_lm | {"charge_up2"},
    ) == {"live1", "charge_never", "rev_never", "charge_up", "rev_up"}
