"""FastmailClient falls back to api.fastmail.com when the session's apiUrl is unreachable."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from lunchsync_sg.fastmail import FALLBACK_API_URL, FastmailClient

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
