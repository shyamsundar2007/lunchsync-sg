"""Minimal read-only Fastmail JMAP client for fetching alert emails."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import requests

SESSION_URL = "https://api.fastmail.com/jmap/session"
_USING = ["urn:ietf:params:jmap:core", "urn:ietf:params:jmap:mail"]
_PAGE = 100


@dataclass(frozen=True)
class EmailMessage:
    """The parts of an email the alert parsers need."""

    message_id: str
    subject: str
    received_at: str
    html: str


class FastmailClient:
    """Fetch emails over JMAP. Needs an API token with read-only Email scope."""

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

    def _call(self, method_calls: list[list[Any]]) -> list[list[Any]]:
        response = self._session.post(
            self._api_url,
            json={"using": _USING, "methodCalls": method_calls},
            timeout=self._timeout,
        )
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
                    "properties": ["messageId", "subject", "receivedAt", "htmlBody", "bodyValues"],
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
                    html="".join(
                        values[part["partId"]]["value"]
                        for part in email["htmlBody"]
                        if part["partId"] in values
                    ),
                ))
            if len(ids) < _PAGE:
                return messages
            position += _PAGE
