"""Tests for the JEV categorization client."""

from unittest.mock import MagicMock, patch

from lunchsync_sg.jev import JevClient


@patch("lunchsync_sg.jev.requests.Session")
def test_categorize_returns_valid_category(mock_session_class: MagicMock) -> None:
    """Test parsing a valid category choice."""
    session = MagicMock()
    mock_session_class.return_value = session
    session.post.return_value.json.return_value = {
        "answers": {
            "category": {
                "type": "choice",
                "choice": "456",
                "confidence": 0.62,
                "probabilities": {"456": 0.62, "unmatched": 0.38},
            }
        }
    }
    client = JevClient("test_key")

    decision = client.categorize(
        {"payee": "Coffee Shop", "amount": "-5.00", "currency": "sgd"},
        [{"id": 456, "name": "Restaurants", "is_group": False}],
    )

    assert decision.category_id == 456
    assert decision.confidence == 0.62
    payload = session.post.call_args.kwargs["json"]
    assert payload["state"]["transaction"]["direction"] == "outgoing"
    assert "456" in payload["questions"]["category"]["criteria"]


@patch("lunchsync_sg.jev.requests.Session")
def test_categorize_handles_unmatched(mock_session_class: MagicMock) -> None:
    """Test leaving an ambiguous transaction uncategorized."""
    session = MagicMock()
    mock_session_class.return_value = session
    session.post.return_value.json.return_value = {
        "answers": {
            "category": {
                "type": "choice",
                "choice": "unmatched",
                "confidence": 0.8,
                "probabilities": {"unmatched": 0.8},
            }
        }
    }

    decision = JevClient("test_key").categorize(
        {"payee": "Unknown"},
        [{"id": 456, "name": "Restaurants", "is_group": False}],
    )

    assert decision.category_id is None
    assert decision.confidence == 0.8
