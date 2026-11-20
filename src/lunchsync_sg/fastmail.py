"""Minimal Fastmail JMAP client: fetch alert emails, then take them out of a label."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import requests

SESSION_URL = "https://api.fastmail.com/jmap/session"
# Used when the session's datacenter-specific apiUrl (e.g. stl.api.fastmail.com) can't be
# reached: api.fastmail.com proxies JMAP calls to the same backend.
FALLBACK_API_URL = "https://api.fastmail.com/jmap/api/"
_USING = ["urn:ietf:params:jmap:core", "urn:ietf:params:jmap:mail"]
_PAGE = 100
# Fastmail label on bank alert emails, removed once an alert is in Lunch Money.
ALERT_LABEL = "Bank"


@dataclass(frozen=True)
class EmailMessage:
    """The parts of an email the alert parsers need."""

    message_id: str
    subject: str
    received_at: str
    html: str
    email_id: str = ""  # JMAP id, needed to change the email
    mailbox_ids: frozenset[str] = frozenset()


class FastmailClient:
    """Fetch emails over JMAP. Needs an API token with Email scope; read-write to remove labels."""

    def __init__(self, token: str, timeout: float = 30) -> None:
        self._session = requests.Session()
        self._session.headers["Authorization"] = f"Bearer {token}"
        self._timeout = timeout
        session = self._get_session()
        self._api_url: str = session["apiUrl"]
        self._account_id: str = session["primaryAccounts"]["urn:ietf:params:jmap:mail"]

    def _get_session(self) -> dict[str, Any]:
        response = self._session.get(SESSION_URL, timeout=self._timeout)
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    def _post(self, method_calls: list[list[Any]]) -> requests.Response:
        return self._session.post(
            self._api_url,
            json={"using": _USING, "methodCalls": method_calls},
            timeout=self._timeout,
        )

    def _call(self, method_calls: list[list[Any]]) -> list[list[Any]]:
        try:
            response = self._post(method_calls)
        except requests.ConnectionError:
            if self._api_url == FALLBACK_API_URL:
                raise
            self._api_url = FALLBACK_API_URL
            response = self._post(method_calls)
        response.raise_for_status()
        responses: list[list[Any]] = response.json()["methodResponses"]
        for name, args, _ in responses:
            if name == "error":
                raise RuntimeError(f"JMAP error: {args.get('type')}")
        return responses

    def fetch_from(self, sender: str, since: datetime) -> list[EmailMessage]:
        """Every email from `sender` received at or after `since` (UTC), oldest first."""
        email_filter = {"from": sender, "after": since.strftime("%Y-%m-%dT%H:%M:%SZ")}
        messages: list[EmailMessage] = []
        position = 0
        while True:
            query, get = self._call([
                ["Email/query", {
                    "accountId": self._account_id,
                    "filter": email_filter,
                    "sort": [{"property": "receivedAt", "isAscending": True}],
                    "position": position,
                    "limit": _PAGE,
                }, "q"],
                ["Email/get", {
                    "accountId": self._account_id,
                    "#ids": {"resultOf": "q", "name": "Email/query", "path": "/ids"},
                    "properties": [
                        "messageId", "subject", "receivedAt", "mailboxIds", "htmlBody", "bodyValues",
                    ],
                    "fetchHTMLBodyValues": True,
                }, "g"],
            ])
            ids: list[str] = query[1]["ids"]
            for email in get[1]["list"]:
                values = email["bodyValues"]
                messages.append(EmailMessage(
                    # No Message-ID header is rare; the JMAP id is stable too.
                    message_id=(email.get("messageId") or [email["id"]])[0],
                    subject=email.get("subject") or "",
                    received_at=email["receivedAt"],
                    email_id=email["id"],
                    mailbox_ids=frozenset(email.get("mailboxIds") or {}),
                    html="".join(
                        values[part["partId"]]["value"]
                        for part in email["htmlBody"]
                        if part["partId"] in values
                    ),
                ))
            if len(ids) < _PAGE:
                return messages
            position += _PAGE

    def _mailboxes(self) -> list[dict[str, Any]]:
        (response,) = self._call([
            ["Mailbox/get", {"accountId": self._account_id, "properties": ["name", "role"]}, "m"],
        ])
        return response[1]["list"]  # type: ignore[no-any-return]

    def remove_label(
        self, emails: list[EmailMessage], label: str, dry_run: bool = False
    ) -> int:
        """Take `emails` out of the mailbox named `label` (any case); return how many changed.

        An email whose only mailbox is `label` moves to Archive, as Fastmail does when
        the last label is removed in the web app. Emails not in `label` are left alone.
        """
        mailboxes = self._mailboxes()
        label_id = next(
            (m["id"] for m in mailboxes if m["name"].casefold() == label.casefold()), None
        )
        if label_id is None:
            raise RuntimeError(f"no Fastmail mailbox named {label!r}")
        archive_id = next((m["id"] for m in mailboxes if m.get("role") == "archive"), None)
        update: dict[str, dict[str, Any]] = {}
        for email in emails:
            if label_id not in email.mailbox_ids:
                continue
            patch: dict[str, Any] = {f"mailboxIds/{label_id}": None}
            if email.mailbox_ids == {label_id}:
                if archive_id is None:
                    raise RuntimeError("no Archive mailbox to move unlabelled emails to")
                patch[f"mailboxIds/{archive_id}"] = True
            update[email.email_id] = patch
        if not update or dry_run:
            return len(update)
        (response,) = self._call([
            ["Email/set", {"accountId": self._account_id, "update": update}, "s"],
        ])
        failed = response[1].get("notUpdated") or {}
        if failed:
            reasons = sorted({f.get("type", "?") for f in failed.values()})
            raise RuntimeError(f"Fastmail did not update {len(failed)} emails: {', '.join(reasons)}")
        return len(update)


def clear_alert_label(
    client: FastmailClient, emails: list[EmailMessage], dry_run: bool, log: Any = print
) -> list[str]:
    """Remove ALERT_LABEL from processed `emails`; return errors instead of raising."""
    try:
        changed = client.remove_label(emails, ALERT_LABEL, dry_run=dry_run)
    except (RuntimeError, requests.RequestException) as e:
        return [f"removing the {ALERT_LABEL} label: {e}"]
    if changed:
        verb = "would remove" if dry_run else "removed"
        log(f"  {verb} the {ALERT_LABEL} label from {changed} emails")
    return []


def settled_references(
    live: list[str], voided: list[tuple[str, str]], in_lunch_money: set[str]
) -> set[str]:
    """External ids of alerts that need nothing more: their emails can lose ALERT_LABEL.

    `live` alerts are settled once in Lunch Money. A (charge, reversal) pair is settled when
    the charge never went up (both are dropped) or when both are in.
    """
    settled = {ref for ref in live if ref in in_lunch_money}
    for charge, reversal in voided:
        if charge not in in_lunch_money or reversal in in_lunch_money:
            settled |= {charge, reversal}
    return settled
