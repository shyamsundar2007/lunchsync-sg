"""Tests for HSBC, DBS, Citi, UOB and OCBC card alert email parsing and sync."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from lunchsync_sg.card_alert_sync import accounts_by_last4, run_card_alert_sync
from lunchsync_sg.card_alerts import (
    SOURCES,
    CardAlertError,
    clean_merchant,
    pair_reversals,
    parse_card_alert,
    to_transaction,
)
from lunchsync_sg.fastmail import EmailMessage
from lunchsync_sg.lunchmoney import UploadResult

HSBC, DBS, CITI, UOB, OCBC = SOURCES

# Same shapes as the banks' real alerts (table cells, <br> separated lines,
# legal footers); merchants, amounts and card numbers are made up.
HSBC_SUBJECT = "Transaction Alerts  (Credit Card)"
DBS_SUBJECT = "Card Transaction Alert"
CITI_SUBJECT = "Citi Alerts - Credit Card/Ready Credit Transaction"
UOB_SUBJECT = "UOB - Transaction Alert"
UOB_REVERSED = "Your transaction has been reversed"
OCBC_SUBJECT = "Card Transaction Alert"


def hsbc(amount: str = "SGD2.20", merchant: str = "KOPI CORNER - CBD", when: str = "05/OCT/2026") -> str:
    rows = [
        ("Card Number", "XXXX-XXXX-XXXX-1111"),
        ("Transaction Date", when),
        ("Transaction Time", "09:20:56"),
        ("Transaction Amount", amount),
        ("Description", merchant),
    ]
    cells = "".join(
        f'<tr><td width="50%"><p style="font-size: 12px;">{k}</p></td>'
        f'<td width="50%"><p style="font-size: 12px;">{v}</p></td></tr>'
        for k, v in rows
    )
    return (
        "<html><body><p>Dear Customer</p><p>Please note there was a transaction made on your "
        f"HSBC credit card.</p><table>{cells}</table><p>You can also log on to the HSBC "
        "Singapore app to view your recent transactions.</p><p>*** This e-mail is "
        "confidential. ***</p></body></html>"
    )


def dbs(amount: str = "SGD15.00", merchant: str = "EXAMPLE AGENCY SINGAPORE SGP") -> str:
    return (
        '<html><body><p>Card Transaction Alert</p><p style="margin: 0 0 15px;">Transaction Ref: '
        "SP0000000000000000000001 </p><p> Dear Sir / Madam, </p><p> We refer to your card "
        "transaction request dated 16/02/26. We are pleased to confirm that the transaction "
        "was completed. </p><p> Date &amp; Time: 16 FEB 15:32 (SGT) <br> Amount: "
        f"{amount} <br> From: DBS/POSB card ending 2222 <br> To: {merchant} </p>"
        "<p> If unauthorised, please login to DBS digibank mobile to report fraud dispute "
        "immediately. </p></body></html>"
    )


def citi(amount: str = "SGD69.00", merchant: str = "EXAMPLE STORE SINGAPORE SGP") -> str:
    lines = [
        "We would like to inform you that there is a charge made on your Citi Rewards Card:",
        "Account number: XXXX-XXXX-XXXX-3333",
        "Transaction date: 10/10/26",
        "Transaction time: 15:02:46",
        f"Transaction amount: {amount}",
        f"Transaction details : {merchant}",
        "If you did not make this request, please call our hotline immediately.",
    ]
    cells = "".join(
        f'<tr><td valign="top" style="font-size: 15px;"> {line} </td></tr>' for line in lines
    )
    return f"<html><body><p>Dear Valued Customer,</p><table>{cells}</table></body></html>"


_UOB_FOOTER = (
    "<p>UOB EMAIL DISCLAIMER: Any person receiving this email shall treat the information "
    "as confidential.</p></body></html>"
)


def uob(amount: str = "SGD 33.80", merchant: str = "Example Taxi Pte Ltd", when: str = "18/10/26") -> str:
    return (
        f"<html><body><p>A transaction of {amount} was made with your UOB Card ending 4444 on "
        f"{when} at {merchant}. If unauthorised, call 24/7 Fraud Hotline now</p>{_UOB_FOOTER}"
    )


def uob_reversed(
    amount: str = "33.80 SGD", merchant: str = "Example Taxi Pte Ltd", when: str = "18 Oct 26, 7:12PM"
) -> str:
    return (
        f"<html><body><p>A transaction of {amount} made with your UOB card ending 4444 on "
        f"{when} at {merchant} has been reversed.</p>{_UOB_FOOTER}"
    )


def ocbc(amount: str = "SGD50.00", merchant: str = "Example Pte. Ltd. SG SGP") -> str:
    return (
        "<html><body><p>Dear Valued Customer</p><p>We wish to inform you that "
        f"{amount} was charged at 19:27 on 19-Feb-26 to your card (-5555) at {merchant}.</p>"
        "<p>Did not make this transaction?</p><ul><li>Lock your card</li></ul></body></html>"
    )


class TestParse:
    def test_hsbc(self) -> None:
        alert = parse_card_alert(HSBC, HSBC_SUBJECT, hsbc(), "<h1>")
        assert alert is not None
        assert (alert.bank, alert.last4) == ("HSBC", "1111")
        assert alert.when == datetime(2026, 10, 5, 9, 20)
        assert (alert.currency, alert.amount) == ("SGD", Decimal("2.20"))
        assert alert.merchant == "KOPI CORNER - CBD"
        assert alert.external_id.startswith("hsbc:")

    def test_hsbc_foreign_currency(self) -> None:
        alert = parse_card_alert(HSBC, HSBC_SUBJECT, hsbc(amount="INR36,162.00"), "<h2>")
        assert alert is not None
        assert (alert.currency, alert.amount) == ("INR", Decimal("36162.00"))

    def test_dbs_takes_year_from_request_date(self) -> None:
        alert = parse_card_alert(DBS, DBS_SUBJECT, dbs(), "<d1>")
        assert alert is not None
        assert (alert.bank, alert.last4) == ("DBS", "2222")
        assert alert.when == datetime(2026, 2, 16, 15, 32)
        assert (alert.currency, alert.amount) == ("SGD", Decimal("15.00"))
        assert alert.merchant == "EXAMPLE AGENCY SINGAPORE SGP"

    def test_citi(self) -> None:
        alert = parse_card_alert(CITI, CITI_SUBJECT, citi(), "<c1>")
        assert alert is not None
        assert (alert.bank, alert.last4) == ("Citi", "3333")
        assert alert.when == datetime(2026, 10, 10, 15, 2)
        assert (alert.currency, alert.amount) == ("SGD", Decimal("69.00"))

    def test_citi_without_currency_uses_merchant_country(self) -> None:
        html = citi(amount="1,146.31", merchant="EXAMPLE CAR HIRE CAIRNS AUS")
        alert = parse_card_alert(CITI, CITI_SUBJECT, html, "<c2>")
        assert alert is not None
        assert (alert.currency, alert.amount) == ("AUD", Decimal("1146.31"))

    def test_citi_without_currency_unknown_country_fails(self) -> None:
        html = citi(amount="100.00", merchant="EXAMPLE SHOP ATLANTIS ZZZ")
        with pytest.raises(CardAlertError, match="ZZZ"):
            parse_card_alert(CITI, CITI_SUBJECT, html, "<c3>")

    def test_uob_charge_has_date_only(self) -> None:
        alert = parse_card_alert(UOB, UOB_SUBJECT, uob(amount="INR 51,350.00"), "<u1>")
        assert alert is not None
        assert (alert.bank, alert.last4, alert.kind) == ("UOB", "4444", "spend")
        assert alert.when == datetime(2026, 10, 18)
        assert (alert.currency, alert.amount) == ("INR", Decimal("51350.00"))
        assert alert.merchant == "Example Taxi Pte Ltd"

    def test_uob_first_transaction(self) -> None:
        html = uob().replace("A transaction of", "The 1st transaction of")
        alert = parse_card_alert(UOB, "UOB - First transaction made on your card", html, "<u2>")
        assert alert is not None
        assert alert.amount == Decimal("33.80")

    def test_uob_reversal(self) -> None:
        alert = parse_card_alert(UOB, UOB_REVERSED, uob_reversed(), "<u3>")
        assert alert is not None
        assert alert.kind == "reversal"
        assert alert.when == datetime(2026, 10, 18, 19, 12)
        assert (alert.currency, alert.amount) == ("SGD", Decimal("33.80"))
        tx = to_transaction(alert, "UOB Card")
        assert tx.amount == Decimal("33.80")
        assert tx.description == "Reversed: Example Taxi Pte Ltd"

    def test_ocbc(self) -> None:
        alert = parse_card_alert(OCBC, OCBC_SUBJECT, ocbc(), "<o1>")
        assert alert is not None
        assert (alert.bank, alert.last4) == ("OCBC", "5555")
        assert alert.when == datetime(2026, 2, 19, 19, 27)
        assert (alert.currency, alert.amount) == ("SGD", Decimal("50.00"))
        assert alert.merchant == "Example Pte. Ltd. SG SGP"

    @pytest.mark.parametrize(
        ("source", "subject"),
        [
            (UOB, "Your eStatement/eAdvice is ready for viewing"),
            (CITI, "Citi Alerts – Credit Card/Ready Credit Payment Received"),
            (CITI, "Threshold Change Alert"),
            (DBS, "digibank Alerts - You've received a transfer"),
            (DBS, "Your Credit Card eStatement is ready"),
        ],
    )
    def test_other_emails_are_ignored(self, source: Any, subject: str) -> None:
        assert parse_card_alert(source, subject, "<p>Something else</p>", "<x>") is None

    @pytest.mark.parametrize(
        ("source", "subject"),
        [
            (HSBC, HSBC_SUBJECT),
            (DBS, DBS_SUBJECT),
            (CITI, CITI_SUBJECT),
            (UOB, UOB_SUBJECT),
            (UOB, UOB_REVERSED),
            (OCBC, OCBC_SUBJECT),
        ],
    )
    def test_unknown_template_fails_loudly(self, source: Any, subject: str) -> None:
        body = "<p>We have refunded SGD 5.00 to your card.</p>"
        with pytest.raises(CardAlertError, match="unrecognised"):
            parse_card_alert(source, subject, body, "<x>")


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("EXAMPLE STORE SINGAPORE SGP", "EXAMPLE STORE"),
        ("Example Pte. Ltd. SG SGP", "Example Pte. Ltd."),
        ("Example Store Singapore SGP", "Example Store"),
        ("EXAMPLE CAR HIRE CAIRNS AUS", "EXAMPLE CAR HIRE CAIRNS AUS"),
        ("KOPI CORNER - CBD", "KOPI CORNER - CBD"),
    ],
)
def test_clean_merchant(raw: str, clean: str) -> None:
    assert clean_merchant(raw) == clean


def test_to_transaction_is_an_expense_on_the_transaction_date() -> None:
    alert = parse_card_alert(CITI, CITI_SUBJECT, citi(), "<c1>")
    assert alert is not None
    tx = to_transaction(alert, "Citi Rewards")
    assert tx.date == date(2026, 10, 10)
    assert tx.amount == Decimal("-69.00")
    assert tx.description == "EXAMPLE STORE"
    assert tx.reference == alert.external_id


class TestPairReversals:
    def alerts(self, *items: tuple[str, str, str]) -> list[Any]:
        out = []
        for subject, html, mid in items:
            alert = parse_card_alert(UOB, subject, html, mid)
            assert alert is not None
            out.append(alert)
        return out

    def test_reversal_voids_matching_charge(self) -> None:
        batch = pair_reversals(self.alerts(
            (UOB_SUBJECT, uob(), "<1>"),
            (UOB_SUBJECT, uob(amount="SGD 4.00", merchant="Kopi"), "<2>"),
            (UOB_REVERSED, uob_reversed(), "<3>"),
        ))
        assert [c.merchant for c in batch.charges] == ["Kopi"]
        assert [(c.message_id, r.message_id) for c, r in batch.voided] == [("<1>", "<3>")]
        assert batch.unmatched_reversals == []

    def test_reversal_without_charge_alert_is_unmatched(self) -> None:
        batch = pair_reversals(self.alerts(
            (UOB_SUBJECT, uob(amount="SGD 33.50"), "<1>"),
            (UOB_REVERSED, uob_reversed(), "<2>"),
        ))
        assert [c.amount for c in batch.charges] == [Decimal("33.50")]
        assert batch.voided == []
        assert [r.message_id for r in batch.unmatched_reversals] == ["<2>"]

    def test_two_holds_two_reversals(self) -> None:
        batch = pair_reversals(self.alerts(
            (UOB_SUBJECT, uob(), "<1>"),
            (UOB_SUBJECT, uob(), "<2>"),
            (UOB_REVERSED, uob_reversed(), "<3>"),
        ))
        assert [c.message_id for c in batch.charges] == ["<2>"]
        assert len(batch.voided) == 1


def test_accounts_by_last4() -> None:
    config = {"accounts": [
        {"card_number": "5400-0000-0000-1111", "name": "A"},
        {"card_number": "2222", "name": "B"},
        {"card_number": "", "name": "C"},
    ]}
    assert accounts_by_last4(config) == {"1111": "A", "2222": "B"}


class TestRunCardAlertSync:
    CONFIG: dict[str, Any] = {
        "accounts": [
            {"card_number": "4000000000001111", "name": "HSBC Card"},
            {"card_number": "5400-0000-0000-2222", "name": "DBS Card"},
            {"card_number": "5400000000003333", "name": "Citi Card"},
            {"card_number": "4000000000004444", "name": "UOB Card"},
        ],
        "lunch_money": {
            "api_key": "lm",
            "account_mapping": {"HSBC Card": 1, "DBS Card": 2, "Citi Card": 3, "UOB Card": 4},
        },
        "card_alerts": {
            "HSBC Card": "2026-10-01", "Citi Card": "2026-10-10", "UOB Card": "2026-02-01",
        },
    }

    def run(
        self,
        emails: dict[str, list[tuple[str, str, str]]],
        existing: set[str] | None = None,
        config: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        def fetch_from(sender: str, since: datetime) -> list[EmailMessage]:
            return [
                EmailMessage(message_id=mid, subject=subject, received_at="", html=html)
                for subject, html, mid in emails.get(sender, [])
            ]

        with (
            patch.dict("os.environ", {"FASTMAIL_API_TOKEN": "fm"}),
            patch("lunchsync_sg.card_alert_sync.FastmailClient") as fastmail,
            patch("lunchsync_sg.card_alert_sync.LunchMoneyClient") as lunch_money,
        ):
            fastmail.return_value.fetch_from.side_effect = fetch_from
            lm = lunch_money.return_value
            lm.get_external_ids.return_value = existing or set()
            lm.upload_transactions.side_effect = lambda txs, *a, **k: UploadResult(
                uploaded=len(txs), skipped=0, errors=[]
            )
            code = run_card_alert_sync(config or self.CONFIG, since=date(2026, 9, 1), **kwargs)
        return code, lm

    @staticmethod
    def uploads(lm: MagicMock) -> dict[str, list[Any]]:
        out: dict[str, list[Any]] = {}
        for call in lm.upload_transactions.call_args_list:
            txs, mapping = call.args
            assert call.kwargs == {"skip_duplicates": False, "apply_rules": True}
            (account,) = mapping
            out[account] = list(txs)
        return out

    def test_uploads_listed_cards_from_their_start_date(self) -> None:
        code, lm = self.run({
            HSBC.sender: [
                (HSBC_SUBJECT, hsbc(when="30/SEP/2026"), "<h0>"),  # before HSBC start
                (HSBC_SUBJECT, hsbc(), "<h1>"),
            ],
            DBS.sender: [(DBS_SUBJECT, dbs(), "<d1>")],  # DBS not listed
            CITI.sender: [(CITI_SUBJECT, citi(), "<c1>")],
        })
        assert code == 0
        uploads = self.uploads(lm)
        assert {a: [tx.date for tx in txs] for a, txs in uploads.items()} == {
            "HSBC Card": [date(2026, 10, 5)],
            "Citi Card": [date(2026, 10, 10)],
        }
        assert lm.upload_transactions.call_args_list[0].args[1] == {"HSBC Card": 1}

    def test_skips_alerts_already_in_lunch_money(self) -> None:
        first = parse_card_alert(HSBC, HSBC_SUBJECT, hsbc(), "<h1>")
        assert first is not None
        code, lm = self.run(
            {HSBC.sender: [
                (HSBC_SUBJECT, hsbc(), "<h1>"),
                (HSBC_SUBJECT, hsbc(amount="SGD4.00"), "<h2>"),
            ]},
            existing={first.external_id},
        )
        assert code == 0
        assert [tx.amount for tx in self.uploads(lm)["HSBC Card"]] == [Decimal("-4.00")]

    def test_reversed_before_upload_sends_nothing(self) -> None:
        code, lm = self.run({UOB.sender: [
            (UOB_SUBJECT, uob(), "<u1>"),
            (UOB_REVERSED, uob_reversed(), "<u2>"),
        ]})
        assert code == 0
        assert self.uploads(lm) == {}
        # The pair was in range and seen, just not uploaded.
        assert lm.get_external_ids.called

    def test_unreversed_charge_is_uploaded(self) -> None:
        code, lm = self.run({UOB.sender: [(UOB_SUBJECT, uob(), "<u1>")]})
        assert code == 0
        assert [tx.amount for tx in self.uploads(lm)["UOB Card"]] == [Decimal("-33.80")]

    def test_reversed_after_upload_sends_credit(self) -> None:
        charge = parse_card_alert(UOB, UOB_SUBJECT, uob(), "<u1>")
        assert charge is not None
        code, lm = self.run(
            {UOB.sender: [
                (UOB_SUBJECT, uob(), "<u1>"),
                (UOB_REVERSED, uob_reversed(), "<u2>"),
            ]},
            existing={charge.external_id},
        )
        assert code == 0
        assert [(tx.amount, tx.description) for tx in self.uploads(lm)["UOB Card"]] == [
            (Decimal("33.80"), "Reversed: Example Taxi Pte Ltd")
        ]

    def test_reversal_already_uploaded_is_not_sent_again(self) -> None:
        charge = parse_card_alert(UOB, UOB_SUBJECT, uob(), "<u1>")
        reversal = parse_card_alert(UOB, UOB_REVERSED, uob_reversed(), "<u2>")
        assert charge is not None and reversal is not None
        code, lm = self.run(
            {UOB.sender: [
                (UOB_SUBJECT, uob(), "<u1>"),
                (UOB_REVERSED, uob_reversed(), "<u2>"),
            ]},
            existing={charge.external_id, reversal.external_id},
        )
        assert code == 0
        assert self.uploads(lm) == {}

    def test_dry_run_uploads_nothing(self) -> None:
        code, lm = self.run({HSBC.sender: [(HSBC_SUBJECT, hsbc(), "<h1>")]}, dry_run=True)
        assert code == 0
        lm.upload_transactions.assert_not_called()

    def test_unparseable_alert_fails_but_uploads_the_rest(self) -> None:
        code, lm = self.run({HSBC.sender: [
            (HSBC_SUBJECT, "<p>A refund was made to your HSBC credit card.</p>", "<h0>"),
            (HSBC_SUBJECT, hsbc(), "<h1>"),
        ]})
        assert code == 1
        assert len(self.uploads(lm)["HSBC Card"]) == 1

    def test_unknown_card_fails(self) -> None:
        config = {**self.CONFIG, "accounts": self.CONFIG["accounts"][1:]}
        code, _ = self.run({HSBC.sender: [(HSBC_SUBJECT, hsbc(), "<h1>")]}, config=config)
        assert code == 1

    def test_listed_card_without_asset_fails(self) -> None:
        config = {**self.CONFIG, "card_alerts": {"Nope": "2026-10-01"}}
        code, lm = self.run({}, config=config)
        assert code == 1
        lm.upload_transactions.assert_not_called()

    def test_nothing_listed_fails(self) -> None:
        config = {k: v for k, v in self.CONFIG.items() if k != "card_alerts"}
        code, _ = self.run({}, config=config)
        assert code == 1
