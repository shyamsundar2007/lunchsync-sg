"""Tests for the email alert sync flags."""

from typing import Any
from unittest.mock import patch

import pytest

from lunchsync_sg.cli import main


def run(argv: list[str], trust: Any = 0, cards: Any = 0) -> tuple[int, list[str]]:
    calls: list[str] = []

    def fake(name: str, result: Any) -> Any:
        def sync(*args: Any, **kwargs: Any) -> int:
            calls.append(name)
            if isinstance(result, Exception):
                raise result
            return int(result)
        return sync

    with (
        patch("sys.argv", ["lunchsync-sg", *argv]),
        patch("lunchsync_sg.cli.load_config", return_value={}),
        patch("lunchsync_sg.trust_sync.run_trust_sync", fake("trust", trust)),
        patch("lunchsync_sg.card_alert_sync.run_card_alert_sync", fake("cards", cards)),
    ):
        return main(), calls


@pytest.mark.parametrize(
    ("flag", "expected"),
    [
        ("--email-alerts", ["trust", "cards"]),
        ("--trust-email", ["trust"]),
        ("--card-alerts", ["cards"]),
    ],
)
def test_flags_choose_syncs(flag: str, expected: list[str]) -> None:
    assert run([flag]) == (0, expected)


def test_failure_in_one_still_runs_the_other() -> None:
    assert run(["--email-alerts"], trust=1) == (1, ["trust", "cards"])


def test_exception_in_one_still_runs_the_other() -> None:
    assert run(["--email-alerts"], trust=RuntimeError("boom")) == (1, ["trust", "cards"])
