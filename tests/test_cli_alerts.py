"""Tests for the --email-alerts flag."""

from typing import Any
from unittest.mock import patch

from lunchsync_sg.cli import main

TRUST = {"lunch_money": {"account_mapping": {"Trust Freedom": 1}}}
CARDS = {"card_alerts": {"HSBC Card": "2026-11-01"}}
BOTH = {**TRUST, **CARDS}


def run(config: dict[str, Any], trust: Any = 0, cards: Any = 0) -> tuple[int, list[str]]:
    calls: list[str] = []

    def fake(name: str, result: Any) -> Any:
        def sync(*args: Any, **kwargs: Any) -> int:
            calls.append(name)
            if isinstance(result, Exception):
                raise result
            return int(result)
        return sync

    with (
        patch("sys.argv", ["lunchsync-sg", "--email-alerts"]),
        patch("lunchsync_sg.cli.load_config", return_value=config),
        patch("lunchsync_sg.trust_sync.run_trust_sync", fake("trust", trust)),
        patch("lunchsync_sg.card_alert_sync.run_card_alert_sync", fake("cards", cards)),
    ):
        return main(), calls


def test_runs_both() -> None:
    assert run(BOTH) == (0, ["trust", "cards"])


def test_runs_only_what_is_set_up() -> None:
    assert run(TRUST) == (0, ["trust"])
    assert run(CARDS) == (0, ["cards"])


def test_nothing_set_up_fails() -> None:
    assert run({}) == (1, [])


def test_failure_in_one_still_runs_the_other() -> None:
    assert run(BOTH, trust=1) == (1, ["trust", "cards"])


def test_exception_in_one_still_runs_the_other() -> None:
    assert run(BOTH, trust=RuntimeError("boom")) == (1, ["trust", "cards"])
