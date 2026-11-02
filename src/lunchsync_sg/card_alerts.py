"""Parse credit card transaction alert emails from HSBC, DBS, Citi, UOB and OCBC.

Each alert becomes one transaction dated on the transaction date. The
statement later carries the posting date. Alerts identify the card by its
last four digits, which map to an account through config.json `accounts`.
UOB also emails when a charge is reversed (a released hold); a reversal
voids the charge it names.
"""

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from lunchsync_sg.models import Transaction
from lunchsync_sg.trust_email import html_to_text

AlertKind = Literal["spend", "reversal"]


class CardAlertError(ValueError):
    """A transaction alert whose body no longer matches the known template."""


@dataclass(frozen=True)
class CardAlert:
    """One card charge alert email."""

    bank: str
    last4: str
    when: datetime  # Singapore time, as printed in the email
    currency: str
    amount: Decimal  # always positive
    merchant: str  # raw, whitespace-collapsed
    message_id: str
    kind: AlertKind = "spend"

    @property
    def external_id(self) -> str:
        """Stable Lunch Money external_id (Message-IDs exceed its 75-char limit)."""
        digest = hashlib.sha256(self.message_id.encode()).hexdigest()[:40]
        return f"{self.bank.lower()}:{digest}"

    @property
    def charge_key(self) -> tuple[str, str, Decimal, str, date]:
        """Fields a reversal shares with the charge it voids."""
        return (self.last4, self.currency, self.amount, self.merchant, self.when.date())


_AMOUNT = r"[\d,]+(?:\.\d{1,2})?"

_HSBC = re.compile(
    r"Please note there was a transaction made on your HSBC credit card\. "
    r"Card Number \S*(?P<last4>\d{4}) "
    r"Transaction Date (?P<date>\d{2}/[A-Z]{3}/\d{4}) Transaction Time (?P<time>\d{2}:\d{2}):\d{2} "
    rf"Transaction Amount (?P<currency>[A-Z]{{3}})(?P<amount>{_AMOUNT}) "
    r"Description (?P<merchant>.+?) You can also log on"
)

_DBS = re.compile(
    r"We refer to your card transaction request dated \d{2}/\d{2}/(?P<year>\d{2})\. "
    r"We are pleased to confirm that the transaction was completed\. "
    r"Date & Time: (?P<day>\d{2} [A-Z]{3}) (?P<time>\d{2}:\d{2}) \(SGT\) "
    rf"Amount: (?P<currency>[A-Z]{{3}})(?P<amount>{_AMOUNT}) "
    r"From: DBS/POSB card ending (?P<last4>\d{4}) "
    r"To: (?P<merchant>.+?) If unauthorised"
)

_CITI = re.compile(
    r"there is a charge made on your Citi .+? Card: "
    r"Account number: \S*(?P<last4>\d{4}) "
    r"Transaction date: (?P<date>\d{2}/\d{2}/\d{2}) Transaction time: (?P<time>\d{2}:\d{2}):\d{2} "
    rf"Transaction amount: (?P<currency>[A-Z]{{3}})?(?P<amount>{_AMOUNT}) "
    r"Transaction details ?: (?P<merchant>.+?) If you did not"
)

_UOB_SPEND = re.compile(
    rf"(?:A|The 1st) transaction of (?P<currency>[A-Z]{{3}}) (?P<amount>{_AMOUNT}) was made "
    r"with your UOB Card ending (?P<last4>\d{4}) on (?P<date>\d{2}/\d{2}/\d{2}) "
    r"at (?P<merchant>.+?)\. If unauthorised"
)

_UOB_REVERSAL = re.compile(
    rf"A transaction of (?P<amount>{_AMOUNT}) (?P<currency>[A-Z]{{3}}) made with your UOB card "
    r"ending (?P<last4>\d{4}) on (?P<when>\d{1,2} \w{3} \d{2}, \d{1,2}:\d{2}[AP]M) "
    r"at (?P<merchant>.+?) has been reversed\."
)

_OCBC = re.compile(
    rf"We wish to inform you that (?P<currency>[A-Z]{{3}})(?P<amount>{_AMOUNT}) was charged "
    r"at (?P<time>\d{2}:\d{2}) on (?P<date>\d{2}-\w{3}-\d{2}) to your card \(-(?P<last4>\d{4})\) "
    r"at (?P<merchant>.+?)\. Did not make this transaction"
)

# Citi omits the currency on some overseas charges; the amount is then in the
# currency of the merchant's country, which ends the merchant string.
_COUNTRY_CURRENCY = {
    "AUS": "AUD", "CAN": "CAD", "CHE": "CHF", "CHN": "CNY", "GBR": "GBP",
    "HKG": "HKD", "IDN": "IDR", "IND": "INR", "JPN": "JPY", "KOR": "KRW",
    "MYS": "MYR", "NZL": "NZD", "PHL": "PHP", "SGP": "SGD", "THA": "THB",
    "TWN": "TWD", "USA": "USD", "VNM": "VND",
    **dict.fromkeys(
        ["AUT", "BEL", "DEU", "ESP", "FIN", "FRA", "GRC", "IRL", "ITA", "NLD", "PRT"],
        "EUR",
    ),
}

# Domestic merchants end in "SINGAPORE SGP" (Citi, DBS) or "SG SGP" (OCBC);
# overseas ones keep city and country.
_DOMESTIC_SUFFIX = re.compile(r"\s+(SINGAPORE|SG)\s+SGP$", re.I)


def _hsbc(text: str, message_id: str) -> CardAlert | None:
    if not (m := _HSBC.search(text)):
        return None
    return CardAlert(
        bank="HSBC",
        last4=m["last4"],
        when=datetime.strptime(f"{m['date']} {m['time']}", "%d/%b/%Y %H:%M"),
        currency=m["currency"],
        amount=Decimal(m["amount"].replace(",", "")),
        merchant=m["merchant"].strip(),
        message_id=message_id,
    )


def _dbs(text: str, message_id: str) -> CardAlert | None:
    if not (m := _DBS.search(text)):
        return None
    return CardAlert(
        bank="DBS",
        last4=m["last4"],
        # The time line has no year; the "dated dd/mm/yy" line does.
        when=datetime.strptime(f"{m['day']} {m['year']} {m['time']}", "%d %b %y %H:%M"),
        currency=m["currency"],
        amount=Decimal(m["amount"].replace(",", "")),
        merchant=m["merchant"].strip(),
        message_id=message_id,
    )


def _citi(text: str, message_id: str) -> CardAlert | None:
    if not (m := _CITI.search(text)):
        return None
    merchant = m["merchant"].strip()
    currency = m["currency"]
    if currency is None:
        country = merchant.rsplit(" ", 1)[-1]
        currency = _COUNTRY_CURRENCY.get(country)
        if currency is None:
            raise CardAlertError(f"Citi alert without currency, unknown country {country!r}")
    return CardAlert(
        bank="Citi",
        last4=m["last4"],
        when=datetime.strptime(f"{m['date']} {m['time']}", "%d/%m/%y %H:%M"),
        currency=currency,
        amount=Decimal(m["amount"].replace(",", "")),
        merchant=merchant,
        message_id=message_id,
    )


def _uob(text: str, message_id: str) -> CardAlert | None:
    if m := _UOB_SPEND.search(text):
        # UOB charge alerts carry a date but no time.
        when = datetime.strptime(m["date"], "%d/%m/%y")
        kind: AlertKind = "spend"
    elif m := _UOB_REVERSAL.search(text):
        when = datetime.strptime(m["when"], "%d %b %y, %I:%M%p")
        kind = "reversal"
    else:
        return None
    return CardAlert(
        bank="UOB",
        last4=m["last4"],
        when=when,
        currency=m["currency"],
        amount=Decimal(m["amount"].replace(",", "")),
        merchant=m["merchant"].strip(),
        message_id=message_id,
        kind=kind,
    )


def _ocbc(text: str, message_id: str) -> CardAlert | None:
    if not (m := _OCBC.search(text)):
        return None
    return CardAlert(
        bank="OCBC",
        last4=m["last4"],
        when=datetime.strptime(f"{m['date']} {m['time']}", "%d-%b-%y %H:%M"),
        currency=m["currency"],
        amount=Decimal(m["amount"].replace(",", "")),
        merchant=m["merchant"].strip(),
        message_id=message_id,
    )


@dataclass(frozen=True)
class AlertSource:
    """Where a bank's alerts come from and how to read them."""

    bank: str
    sender: str
    # Subjects of alerts that must parse; anything else from the sender is ignored.
    subject: re.Pattern[str]
    parse: Callable[[str, str], CardAlert | None]


SOURCES = [
    AlertSource(
        "HSBC",
        "HSBC.Bank.Singapore.Limited@notification.hsbc.com.hk",
        re.compile(r"^Transaction Alerts\s+\(Credit Card\)$"),
        _hsbc,
    ),
    AlertSource("DBS", "ibanking.alert@dbs.com", re.compile(r"^Card Transaction Alert$"), _dbs),
    AlertSource(
        "Citi",
        "alerts@citibank.com.sg",
        re.compile(r"Credit Card/Ready Credit Transaction$"),
        _citi,
    ),
    AlertSource(
        "UOB",
        "unialerts@uobgroup.com",
        re.compile(
            r"^(UOB - Transaction Alert|UOB - First transaction made on your card"
            r"|Your transaction has been reversed)$"
        ),
        _uob,
    ),
    AlertSource("OCBC", "noreply@notify.ocbc.com", re.compile(r"^Card Transaction Alert$"), _ocbc),
]


def parse_card_alert(
    source: AlertSource, subject: str, body_html: str, message_id: str
) -> CardAlert | None:
    """Parse one email from a bank's alert sender.

    Returns None for emails that are not card charge alerts (payments,
    statements, transfers). Raises CardAlertError when a charge alert does
    not match the known template, so a template change (or a refund
    template not seen yet) fails loudly instead of silently dropping spend.
    """
    if not source.subject.search(subject.strip()):
        return None
    alert = source.parse(html_to_text(body_html), message_id)
    if alert is None:
        raise CardAlertError(f"unrecognised {source.bank} card alert: {subject!r}")
    return alert


def clean_merchant(merchant: str) -> str:
    """Drop the "SINGAPORE SGP" / "SG SGP" suffix domestic merchants carry."""
    return _DOMESTIC_SUFFIX.sub("", merchant)


def to_transaction(alert: CardAlert, account: str) -> Transaction:
    """An alert as a Lunch Money transaction dated on the transaction date.

    A charge is an expense; a reversal is a credit that offsets it.
    """
    payee = clean_merchant(alert.merchant)
    if alert.kind == "reversal":
        payee = f"Reversed: {payee}"
    return Transaction(
        date=alert.when.date(),
        description=payee,
        amount=alert.amount if alert.kind == "reversal" else -alert.amount,
        account=account,
        original_currency=alert.currency,
        reference=alert.external_id,
    )


@dataclass
class AlertBatch:
    """A source's alerts, with each reversal paired to the charge it voids."""

    charges: list[CardAlert]  # charges no reversal voids
    # (charge, reversal) pairs. Upload neither if the charge is not in Lunch
    # Money yet; upload the reversal as a credit if the charge went up earlier.
    voided: list[tuple[CardAlert, CardAlert]]
    # Reversals of holds that never sent a charge alert; nothing to undo.
    unmatched_reversals: list[CardAlert]


def pair_reversals(alerts: list[CardAlert]) -> AlertBatch:
    """Pair each reversal with the earliest unvoided charge it matches."""
    alerts = sorted(alerts, key=lambda a: (a.when, a.message_id))
    charges = [a for a in alerts if a.kind == "spend"]
    voided: list[tuple[CardAlert, CardAlert]] = []
    unmatched: list[CardAlert] = []
    for reversal in (a for a in alerts if a.kind == "reversal"):
        match = next((c for c in charges if c.charge_key == reversal.charge_key), None)
        if match is None:
            unmatched.append(reversal)
            continue
        charges.remove(match)
        voided.append((match, reversal))
    return AlertBatch(charges=charges, voided=voided, unmatched_reversals=unmatched)
