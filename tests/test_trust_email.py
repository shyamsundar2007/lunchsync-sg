"""Tests for Trust Bank alert email parsing and sync."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from lunchsync_sg.fastmail import EmailMessage
from lunchsync_sg.lunchmoney import UploadResult, generate_external_id
from lunchsync_sg.trust_email import (
    TrustAlertError,
    build_batch,
    clean_merchant,
    html_to_text,
    parse_alert,
)
from lunchsync_sg.trust_sync import run_trust_sync

# Same shape as Trust's real alerts (commented-out preheader, nested spans,
# padded merchant strings); merchants and amounts are made up.
_WRAPPER = """<html><head><style>.x {{ color: #fff; }}</style></head><body>
<!-- <tr><td>96 Didn't do this? Please contact us via your Trust App.</td></tr> -->
<table><tr><td class="x "><div><p style="Margin:0;"><span
  style="font-size:18px;">{sentence}<br><br></span><br><br></p></div></td></tr></table>
<p>Trust Bank Singapore Ltd | Reg No. 202039712G</p></body></html>"""

SPEND = (
    "You&#39;ve spent SGD 1,234.50 at Kopi Corner   SG   123456   Singapore SG on "
    "22 Oct 2026 20:25SGT with Freedom credit card. You’ll receive estimated "
    "130.00 Trust Miles*. Not you? Alert us via the Trust App."
)
SPEND_FX = (
    "You've spent USD 12.00 at Example Store San Francisco US on 3 Nov 2026 01:05SGT "
    "with Freedom credit card. Not you? Alert us via the Trust App."
)
SPEND_OVERSEAS = (
    "0% FX fees! You&#39;ve spent USD 25.00 using Freedom credit card at EXAMPLE*VISA "
    "OFFICE New Delhi IN on 28 Oct 2026 19:02SGT. Not you? Alert us via Trust App."
)
CANCEL = (
    "We've cancelled your purchase of SGD 1.00 at Grab* Singapore SG on "
    "23 Oct 2026 11:28SGT with Freedom credit card."
)
HOLD = (
    "You've spent SGD 1.00 at Grab* Singapore SG on 23 Oct 2026 11:28SGT with "
    "Freedom credit card. Not you? Alert us via the Trust App."
)
REFUND = (
    "We've refunded SGD 5.00 from Bookshop Pte. Ltd.        SG           00000   SG  "
    "to your Trust card on 26 Oct 2026 19:26SGT. Tap to view your account."
)


def email(sentence: str) -> str:
    return _WRAPPER.format(sentence=sentence)


class TestParseAlert:
    def test_spend(self) -> None:
        alert = parse_alert("Yay! Transaction successful 😁", email(SPEND), "<a@ses>")
        assert alert is not None
        assert alert.kind == "spend"
        assert alert.amount == Decimal("1234.50")
        assert alert.currency == "SGD"
        assert alert.when == datetime(2026, 10, 22, 20, 25)
        assert alert.merchant == "Kopi Corner SG 123456 Singapore SG"

    def test_foreign_currency(self) -> None:
        alert = parse_alert("Yay! Transaction successful 😁", email(SPEND_FX), "<b@ses>")
        assert alert is not None
        assert (alert.currency, alert.amount) == ("USD", Decimal("12.00"))

    def test_overseas(self) -> None:
        alert = parse_alert(
            "Yay! Overseas transaction successful 😁", email(SPEND_OVERSEAS), "<o@ses>"
        )
        assert alert is not None
        assert alert.kind == "spend"
        assert (alert.currency, alert.amount) == ("USD", Decimal("25.00"))
        assert alert.when == datetime(2026, 10, 28, 19, 2)
        assert alert.merchant == "EXAMPLE*VISA OFFICE New Delhi IN"

    def test_cancel(self) -> None:
        alert = parse_alert("Oops! Transaction cancelled 💳", email(CANCEL), "<c@ses>")
        assert alert is not None
        assert alert.kind == "cancel"
        assert alert.merchant == "Grab* Singapore SG"

    def test_refund(self) -> None:
        alert = parse_alert("Ta-da! Transaction refunded 🙂", email(REFUND), "<d@ses>")
        assert alert is not None
        assert alert.kind == "refund"
        assert alert.amount == Decimal("5.00")
        assert alert.merchant == "Bookshop Pte. Ltd. SG 00000 SG"

    def test_ignores_non_transaction_email(self) -> None:
        body = email("Yay! Your Paynow transfer's a success.")
        assert parse_alert("Yay! Your Paynow transfer's a success.", body, "<e@ses>") is None

    def test_unknown_transaction_template_raises(self) -> None:
        body = email("Your Freedom card was charged SGD 4.00 at Somewhere.")
        with pytest.raises(TrustAlertError):
            parse_alert("Yay! Transaction successful 😁", body, "<f@ses>")

    def test_external_id_fits_lunch_money_limit(self) -> None:
        alert = parse_alert("Transaction successful", email(SPEND), "<" + "x" * 120 + ">")
        assert alert is not None
        assert len(alert.external_id) <= 75
        assert alert.external_id.startswith("trust:")


def test_html_to_text_drops_comments_and_styles() -> None:
    text = html_to_text(email("Hello &amp; bye"))
    assert "Didn't do this" not in text
    assert "color" not in text
    assert "Hello & bye" in text


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("Kopi Corner SG 123456 Singapore SG", "Kopi Corner"),
        ("SHOPEE APPLEPAY 62708100 SG", "SHOPEE APPLEPAY"),
        ("BEACH HOTEL 1886 L SINGAPORE SG", "BEACH HOTEL 1886 L"),
        ("Grab* KHE3E2-G-2 Singapore SG", "Grab* KHE3E2-G-2"),
        ("Example Store San Francisco US", "Example Store San Francisco US"),
        ("7-ELEVEN SG", "7-ELEVEN"),
        ("SG", "SG"),
    ],
)
def test_clean_merchant(raw: str, clean: str) -> None:
    assert clean_merchant(raw) == clean


def alerts(*pairs: tuple[str, str]) -> list[Any]:
    parsed = [parse_alert("Transaction", email(s), mid) for s, mid in pairs]
    assert all(parsed)
    return parsed


class TestBuildBatch:
    def test_signs_and_payees(self) -> None:
        batch = build_batch(alerts((SPEND, "<1>"), (REFUND, "<2>")), "Trust Freedom")
        spend, refund = batch.transactions
        assert (spend.amount, spend.description, spend.date) == (
            Decimal("-1234.50"), "Kopi Corner", date(2026, 10, 22),
        )
        assert (refund.amount, refund.description) == (Decimal("5.00"), "Bookshop Pte. Ltd.")
        assert spend.account == "Trust Freedom"
        assert batch.voided == []

    def test_cancellation_voids_its_purchase(self) -> None:
        batch = build_batch(alerts((HOLD, "<1>"), (CANCEL, "<2>"), (SPEND, "<3>")), "T")
        assert [tx.description for tx in batch.transactions] == ["Kopi Corner"]
        ((purchase, cancellation),) = batch.voided
        assert purchase.amount == Decimal("-1.00")
        assert cancellation.amount == Decimal("1.00")
        assert cancellation.description == "Cancelled: Grab*"

    def test_cancellation_voids_only_one_identical_purchase(self) -> None:
        batch = build_batch(alerts((HOLD, "<1>"), (HOLD, "<2>"), (CANCEL, "<3>")), "T")
        assert [tx.amount for tx in batch.transactions] == [Decimal("-1.00")]
        assert len(batch.voided) == 1

    def test_identical_purchases_both_kept(self) -> None:
        batch = build_batch(alerts((HOLD, "<1>"), (HOLD, "<2>")), "T")
        ids = {generate_external_id(tx) for tx in batch.transactions}
        assert len(ids) == 2

    def test_cancellation_without_purchase_is_a_credit(self) -> None:
        batch = build_batch(alerts((CANCEL, "<1>")), "T")
        (tx,) = batch.transactions
        assert tx.amount == Decimal("1.00")
        assert tx.description == "Cancelled: Grab*"


class TestRunTrustSync:
    CONFIG: dict[str, Any] = {
        "lunch_money": {"api_key": "lm", "account_mapping": {"Trust Freedom": 42}},
    }

    def run(self, sentences: list[tuple[str, str]], existing: set[str], **kwargs: Any) -> Any:
        emails = [
            EmailMessage(
                message_id=mid, subject="Yay! Transaction successful", received_at="", html=email(s)
            )
            for s, mid in sentences
        ]
        with (
            patch.dict("os.environ", {"FASTMAIL_API_TOKEN": "fm"}),
            patch("lunchsync_sg.trust_sync.FastmailClient") as fastmail,
            patch("lunchsync_sg.trust_sync.LunchMoneyClient") as lunch_money,
        ):
            fastmail.return_value.fetch_from.return_value = emails
            lm = lunch_money.return_value
            lm.get_external_ids.return_value = existing
            lm.upload_transactions.side_effect = lambda txs, *a, **k: UploadResult(
                uploaded=len(txs), skipped=0, errors=[]
            )
            code = run_trust_sync(self.CONFIG, since=date(2026, 10, 1), **kwargs)
        return code, lm

    def uploaded(self, lm: MagicMock) -> list[Any]:
        if not lm.upload_transactions.called:
            return []
        txs, mapping = lm.upload_transactions.call_args.args
        assert mapping == {"Trust Freedom": 42}
        assert lm.upload_transactions.call_args.kwargs == {"skip_duplicates": False, "apply_rules": True}
        return list(txs)

    def test_uploads_only_new(self) -> None:
        first = alerts((SPEND, "<1>"))[0].external_id
        code, lm = self.run([(SPEND, "<1>"), (REFUND, "<2>")], existing={first})
        assert code == 0
        assert [tx.description for tx in self.uploaded(lm)] == ["Bookshop Pte. Ltd."]

    def test_cancelled_before_upload_sends_nothing(self) -> None:
        code, lm = self.run([(HOLD, "<1>"), (CANCEL, "<2>")], existing=set())
        assert code == 0
        assert self.uploaded(lm) == []

    def test_cancelled_after_upload_sends_credit(self) -> None:
        hold = alerts((HOLD, "<1>"))[0].external_id
        code, lm = self.run([(HOLD, "<1>"), (CANCEL, "<2>")], existing={hold})
        assert code == 0
        assert [tx.amount for tx in self.uploaded(lm)] == [Decimal("1.00")]

    def test_dry_run_uploads_nothing(self) -> None:
        code, lm = self.run([(SPEND, "<1>")], existing=set(), dry_run=True)
        assert code == 0
        lm.upload_transactions.assert_not_called()

    def test_unparseable_alert_fails_but_uploads_the_rest(self) -> None:
        bad = "Your Freedom card was charged SGD 4.00 at Somewhere."
        code, lm = self.run([(bad, "<1>"), (SPEND, "<2>")], existing=set())
        assert code == 1
        assert len(self.uploaded(lm)) == 1

    def test_missing_token(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            assert run_trust_sync(self.CONFIG) == 1
