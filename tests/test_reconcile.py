"""Tests for reconciling statement exports with Lunch Money."""

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import patch

from lunchsync_sg.lunchmoney import UploadResult, generate_external_id
from lunchsync_sg.models import Transaction
from lunchsync_sg.parsers import DBSCreditParser, UOBCreditParser
from lunchsync_sg.reconcile import merchant_overlap, plan_account, run_reconcile

ACCOUNT = "Card"


def line(day: str, amount: str, desc: str = "KOPI CORNER SINGAPORE", currency: str = "SGD") -> Transaction:
    return Transaction(
        date=date.fromisoformat(day), description=desc, amount=Decimal(amount),
        account=ACCOUNT, original_currency=currency,
    )


_ids = iter(range(1, 10_000))


def row(
    day: str, amount: str, payee: str = "KOPI CORNER", ext: str | None = "uob:abc",
    currency: str = "sgd", notes: str | None = None,
) -> dict[str, Any]:
    """A Lunch Money row; `amount` uses Lunch Money's sign (positive = expense)."""
    return {
        "id": next(_ids), "date": day, "amount": amount, "payee": payee,
        "external_id": ext, "currency": currency, "notes": notes,
    }


def plan(lines: list[Transaction], rows: list[dict[str, Any]]) -> Any:
    return plan_account(ACCOUNT, 7, lines, rows)


class TestPlanAccount:
    def test_alert_row_moves_to_posting_date(self) -> None:
        alert = row("2026-11-12", "1.8600", "BUS/MRT")
        p = plan([line("2026-11-14", "-1.86", "BUS/MRT 945318554 SINGAPORE")], [alert])
        assert [u.row["id"] for u in p.updates] == [alert["id"]]
        assert p.updates[0].fields == {"date": "2026-11-14", "notes": "txn date 2026-11-12"}
        assert p.inserts == []

    def test_existing_note_is_kept(self) -> None:
        alert = row("2026-11-12", "1.8600", notes="work trip")
        p = plan([line("2026-11-13", "-1.86")], [alert])
        assert p.updates[0].fields["notes"] == "work trip · txn date 2026-11-12"

    def test_alert_row_on_posting_date_is_confirmed(self) -> None:
        # Bank-account lines post the same day, and a second run finds the
        # rows the first run moved: nothing to change either way.
        p = plan([line("2026-11-02", "-5.00")], [row("2026-11-02", "5.0000")])
        assert (p.confirmed, p.updates, p.inserts) == (1, [], [])

    def test_foreign_alert_takes_sgd_amount(self) -> None:
        alert = row("2026-10-16", "51350.0000", "RAZ*IndiGo", currency="inr")
        p = plan([line("2026-10-19", "-718.79", "RAZ*IndiGo Gurgaon")], [alert])
        assert p.updates[0].fields == {
            "date": "2026-10-19", "notes": "txn date 2026-10-16",
            "amount": -718.79, "currency": "sgd",
        }

    def test_foreign_alert_needs_a_shared_merchant_word(self) -> None:
        alert = row("2026-10-16", "51350.0000", "RAZ*IndiGo", currency="inr")
        p = plan([line("2026-10-19", "-718.79", "SOMEWHERE ELSE")], [alert])
        assert p.updates == [] and len(p.inserts) == 1
        assert p.unposted_alerts == [alert]

    def test_line_already_imported_is_skipped(self) -> None:
        tx = line("2026-10-13", "-11.50", "Salad Stop")
        p = plan([tx], [row("2026-10-13", "11.5000", ext=generate_external_id(tx))])
        assert (p.already_in, p.inserts, p.updates) == (1, [], [])

    def test_earlier_import_with_other_description_is_skipped(self) -> None:
        p = plan(
            [line("2026-10-26", "-107.91", "D-260711090258 EnriIVPT First GIRO")],
            [row("2026-10-26", "107.9100", "D-260711090258My Enri First GIRO", ext="0f1e2d")],
        )
        assert (p.already_in, p.inserts) == (1, [])

    def test_missing_line_is_added(self) -> None:
        tx = line("2026-11-01", "0.44", "CREDIT INTEREST")
        p = plan([tx], [])
        assert p.inserts == [tx]

    def test_amount_and_direction_must_match(self) -> None:
        p = plan([line("2026-11-13", "811.17", "AIRBNB")], [row("2026-11-12", "811.1700", "AIRBNB")])
        assert p.updates == [] and len(p.inserts) == 1

    def test_alert_older_than_a_week_is_not_matched(self) -> None:
        p = plan([line("2026-11-20", "-5.00")], [row("2026-11-12", "5.0000")])
        assert p.updates == [] and len(p.inserts) == 1

    def test_each_row_matches_one_line(self) -> None:
        rows = [row("2026-11-12", "1.8600"), row("2026-11-12", "1.8600")]
        p = plan([line("2026-11-13", "-1.86"), line("2026-11-13", "-1.86"), line("2026-11-13", "-1.86")], rows)
        assert len(p.updates) == 2 and len(p.inserts) == 1

    def test_closest_date_then_best_merchant_wins(self) -> None:
        far = row("2026-11-10", "4.0000", "TOAST BOX")
        near_other = row("2026-11-12", "4.0000", "GRAB")
        near_same = row("2026-11-12", "4.0000", "TOAST BOX")
        p = plan([line("2026-11-13", "-4.00", "TOAST BOX - TBP SINGAPORE")], [far, near_other, near_same])
        assert p.updates[0].row is near_same

    def test_unmatched_alert_rows_in_range_are_reported(self) -> None:
        pending = row("2026-11-14", "51.5600", "VIEWQWEST")
        p = plan([line("2026-11-14", "-6.15", "MYREPUBLIC")], [pending])
        assert p.unposted_alerts == [pending]

    def test_csv_rows_are_not_reported_as_unposted(self) -> None:
        p = plan([line("2026-11-14", "-6.15")], [row("2026-11-14", "9.9900", ext="0f1e2d")])
        assert p.unposted_alerts == []


def test_merchant_overlap() -> None:
    assert merchant_overlap("TOAST BOX - TBP SINGAPORE", "Toast Box") == 2
    assert merchant_overlap("BUS/MRT", "GRAB*") == 0


class TestRunReconcile:
    CONFIG: dict[str, Any] = {
        "accounts": [{"card_number": "5420-0000-0000-1111", "name": "Card", "bank": "DBS", "type": "credit_card"}],
        "lunch_money": {"api_key": "lm", "account_mapping": {"Card": 7}},
    }
    CSV = (
        '"Card Transaction Details For:","DBS MasterCard World 5420-0000-0000-1111",,,,,,\n'
        '"Transaction Date","Transaction Posting Date","Transaction Description",'
        '"Transaction Type","Payment Type","Transaction Status","Debit Amount","Credit Amount"\n'
        '"14 Nov 2026","14 Nov 2026","PENDING SHOP","","","Pending","9.00",""\n'
        '"12 Nov 2026","13 Nov 2026","KOPI CORNER SINGAPORE SGP","PURCHASE","","Settled","4.00",""\n'
        '"12 Nov 2026","13 Nov 2026","NEW SHOP SINGAPORE SGP","PURCHASE","","Settled","6.15",""\n'
    )

    def run(self, tmp_path: Path, apply: bool) -> Any:
        f = tmp_path / "dbs.csv"
        f.write_text(self.CSV)
        alert = row("2026-11-12", "4.0000", "KOPI CORNER", ext="dbs:1")
        with patch("lunchsync_sg.reconcile.LunchMoneyClient") as client:
            lm = client.return_value
            lm.get_transactions.return_value = [alert]
            lm.upload_transactions.side_effect = lambda txs, *a, **k: UploadResult(len(txs), 0, [])
            code = run_reconcile(self.CONFIG, [tmp_path], apply=apply)
        return code, lm, alert

    def test_preview_changes_nothing(self, tmp_path: Path) -> None:
        code, lm, _ = self.run(tmp_path, apply=False)
        assert code == 0
        lm.update_transaction.assert_not_called()
        lm.upload_transactions.assert_not_called()

    def test_apply_updates_and_adds(self, tmp_path: Path) -> None:
        code, lm, alert = self.run(tmp_path, apply=True)
        assert code == 0
        lm.update_transaction.assert_called_once_with(
            alert["id"], {"date": "2026-11-13", "notes": "txn date 2026-11-12"}
        )
        (txs, mapping), kwargs = lm.upload_transactions.call_args
        assert [t.description for t in txs] == ["NEW SHOP SINGAPORE"]
        assert mapping == {"Card": 7}
        assert kwargs == {"skip_duplicates": False, "apply_rules": True}

    def test_unmapped_account_fails(self, tmp_path: Path) -> None:
        config = {**self.CONFIG, "lunch_money": {"api_key": "lm", "account_mapping": {}}}
        f = tmp_path / "dbs.csv"
        f.write_text(self.CSV)
        with patch("lunchsync_sg.reconcile.LunchMoneyClient"):
            assert run_reconcile(config, [f]) == 1


UOB_EXPORT = (
    "United Overseas Bank Limited. Company Reg No. 000000000Z,,,,,,\n"
    "Account Number:,4000000000001111,,,,,\n"
    "Account Type:,PREFERRED VISA,,,,,\n"
    "Transaction Date,Posting Date,Description,Foreign Currency Type,"
    "Transaction Amount(Foreign),Local Currency Type,Transaction Amount(Local)\n"
    "14 Nov 2026,,BUS/MRT SINGAPORE SG ,,,SGD,4.25\n"
    ",,Previous Balance,,,SGD,20.00\n"
    '12 Oct 2026,13 Oct 2026,"Toast Box Singapore SG\nRef No: 111",,,SGD,6.10\n'
    '12 Oct 2026,13 Oct 2026,"Toast Box Singapore SG\nRef No: 222",,,SGD,6.10\n'
    "14 Nov 2026,,BUS/MRT SINGAPORE SG ,,,SGD,4.25\n"
    ",,Previous Balance,,,SGD,20.00\n"
    '12 Oct 2026,13 Oct 2026,"Toast Box Singapore SG\nRef No: 111",,,SGD,6.10\n'
    '12 Oct 2026,13 Oct 2026,"Toast Box Singapore SG\nRef No: 222",,,SGD,6.10\n'
)


def test_uob_skips_unposted_and_repeated_rows() -> None:
    parser = UOBCreditParser()
    txs = parser.parse(UOB_EXPORT)
    # Two real purchases (different Ref No) kept once each; repeat and unposted dropped.
    assert [(t.date, t.amount) for t in txs] == [(date(2026, 10, 13), Decimal("-6.10"))] * 2
    assert parser.pending_skipped == 2


def test_dbs_card_uses_posting_date() -> None:
    txs = DBSCreditParser().parse(TestRunReconcile.CSV)
    assert [t.date for t in txs] == [date(2026, 11, 13)] * 2
