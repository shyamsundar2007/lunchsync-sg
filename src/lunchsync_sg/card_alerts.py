"""Parse credit card transaction alert emails from HSBC, DBS and Citi.

Each alert becomes one transaction dated on the transaction date. The
statement later carries the posting date. Alerts identify the card by its
last four digits, which map to an account through config.json `accounts`.
"""

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from lunchsync_sg.models import Transaction
from lunchsync_sg.trust_email import html_to_text


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

    @property
    def external_id(self) -> str:
        """Stable Lunch Money external_id (Message-IDs exceed its 75-char limit)."""
        digest = hashlib.sha256(self.message_id.encode()).hexdigest()[:40]
        return f"{self.bank.lower()}:{digest}"


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

# Domestic merchants end in "SINGAPORE SGP"; overseas ones keep city and country.
_DOMESTIC_SUFFIX = re.compile(r"\s+SINGAPORE\s+SGP$", re.I)


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
    """Drop the "SINGAPORE SGP" suffix domestic merchants carry."""
    return _DOMESTIC_SUFFIX.sub("", merchant)


def to_transaction(alert: CardAlert, account: str) -> Transaction:
    """A charge alert as a Lunch Money expense dated on the transaction date."""
    return Transaction(
        date=alert.when.date(),
        description=clean_merchant(alert.merchant),
        amount=-alert.amount,
        account=account,
        original_currency=alert.currency,
        reference=alert.external_id,
    )
