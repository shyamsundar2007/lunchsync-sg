"""Parse transaction alert emails from HSBC, DBS, Citi, UOB and OCBC.

Covers credit card charges, plus the OCBC 360 bank account (PayNow, NETS QR,
transfers, deposits, withdrawals) and DBS savings (received transfers, bill
payments, NETS). Each alert becomes one transaction dated
on the transaction date; the statement later carries the posting date.
Alerts identify the card or account by its last four digits, which map to an
account through config.json `accounts`. UOB also emails when a charge is
reversed (a released hold); a reversal voids the charge it names.
"""

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from lunchsync_sg.models import Transaction
from lunchsync_sg.trust_email import html_to_text

# spend: money out. reversal: a released hold, offsets its charge. credit: money in.
AlertKind = Literal["spend", "reversal", "credit"]


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

# DBS savings account alerts. Bill payment and NETS alerts have no year.
_DBS_ACCOUNT: list[tuple[AlertKind, re.Pattern[str]]] = [
    ("credit", re.compile(
        rf"You have received (?P<currency>[A-Z]{{3}}) (?P<amount>{_AMOUNT}) via .+? on "
        r"(?P<date>\d{1,2} \w{3} \d{4}) (?P<time>\d{2}:\d{2}) SGT\. "
        r"From: (?P<merchant>.+?) To: Your DBS/ ?POSB account ending (?P<last4>\d{4})"
    )),
    ("spend", re.compile(
        r"You.ve successfully made a bill payment\. "
        r"Date and Time: (?P<day>\d{1,2} \w{3}) (?P<time>\d{2}:\d{2}) \(SGT\) "
        rf"Amount: (?P<currency>[A-Z]{{3}}) (?P<amount>{_AMOUNT}) "
        r"From: .*?\(A/C ending (?P<last4>\d{4})\) To: (?P<merchant>.+?) If unauthorised"
    )),
    ("spend", re.compile(
        r"NETS Scan & Pay transaction on .+? was successful\. "
        r"Date & Time: (?P<day>\d{1,2} \w{3}) (?P<time>\d{2}:\d{2}) SGT "
        rf"Amount: S\$(?P<amount>{_AMOUNT}) "
        r"From: DBS/POSB Account ending (?P<last4>\d{4}) To: (?P<merchant>.+?) If unauthorised"
    )),
]

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

# OCBC 360 account alerts. Times are 12- or 24-hour, with or without AM/PM
# ("11:28 AM", "14:52 PM", "12:08pm", "12.00 PM").
_O_DATE = r"(?P<date>\d{1,2} \w{3} \d{4})"
_O_TIME = r"(?P<time>\d{1,2}[:.]\d{2}) ?(?P<ampm>[AaPp][Mm])?"
_O_AMOUNT = rf"(?P<currency>[A-Z]{{3}}) (?P<amount>{_AMOUNT})"
_O_FROM = r"From your account : .*?\(-\d*(?P<last4>\d{4})\)"

_OCBC_ACCOUNT: list[tuple[AlertKind, re.Pattern[str]]] = [
    ("spend", re.compile(
        rf"The following PayNow transfer has been made to (?P<merchant>.+?) using .+? "
        rf"Date : {_O_DATE} Time : {_O_TIME} SGT Amount : {_O_AMOUNT} {_O_FROM} "
        r"Description : (?P<note>.*?) ?Reference number"
    )),
    ("spend", re.compile(
        rf"The following NETS QR payment has been made: Date : {_O_DATE} Time : {_O_TIME} SGT "
        rf"Amount : {_O_AMOUNT} {_O_FROM} To : (?P<merchant>.+?) NETS merchant ID"
    )),
    ("spend", re.compile(
        r"we have sent money to (?P<merchant>.+?) using Virtual Payment Address .+? "
        rf"Date of Transfer : {_O_DATE} Time of Transfer : {_O_TIME} SGT Amount : {_O_AMOUNT} "
        rf"{_O_FROM} Description/reference no\."
    )),
    ("spend", re.compile(
        r"We have received your request to make the following transfer: "
        rf"Date of Transfer : {_O_DATE} Time of Transfer : {_O_TIME} SGT Amount : {_O_AMOUNT} "
        rf"{_O_FROM} To account : (?P<merchant>.+?) Reference number"
    )),
    # One deposit template leaves out the date; the email's arrival date is used.
    ("credit", re.compile(
        rf"A deposit was made in your account\. Here are the details: (?:Date of deposit: {_O_DATE} )?"
        rf"Time of deposit: {_O_TIME} Amount: {_O_AMOUNT} "
        r"Account that money was deposited in: \(-\d*(?P<last4>\d{4})\) "
        r"Reference: (?P<merchant>.+?)(?: Mode of transfer:| For assistance| If you have|$)"
    )),
    ("spend", re.compile(
        rf"A sum of {_O_AMOUNT} was withdrawn from your account \(-\d*(?P<last4>\d{{4}})\) "
        rf"at {_O_TIME} on {_O_DATE}\.(?P<withdrawal>)"
    )),
    ("spend", re.compile(
        r"we have deposited your contribution in your SRS Account: "
        r"SRS Contribution Date : (?P<numdate>\d{2}/\d{2}/\d{4}) "
        rf"Amount : {_O_AMOUNT} From Account : X*(?P<last4>\d{{4}}) .*?Status : Successful(?P<srs>)"
    )),
]

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

# Domestic merchants end in "SINGAPORE SGP" (Citi, DBS), "SG SGP" or
# "Singapore SG" (OCBC); overseas ones keep city and country.
_DOMESTIC_SUFFIX = re.compile(r"\s+(SINGAPORE|SG)\s+SGP?$", re.I)


def _hsbc(text: str, message_id: str, received: datetime | None) -> CardAlert | None:
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


def _with_year(day_month: str, time: str, received: datetime | None) -> datetime:
    """A "dd Mon" date in the year the email arrived (or the one before, across New Year)."""
    if received is None:
        raise CardAlertError(f"alert date {day_month!r} has no year and no arrival time")
    when = datetime.strptime(f"{day_month} {received.year} {time}", "%d %b %Y %H:%M")
    if when > received + timedelta(days=1):
        when = when.replace(year=received.year - 1)
    return when


def _dbs(text: str, message_id: str, received: datetime | None) -> CardAlert | None:
    if not (m := _DBS.search(text)):
        return _dbs_account(text, message_id, received)
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


def _dbs_account(text: str, message_id: str, received: datetime | None) -> CardAlert | None:
    found = next(
        ((kind, m) for kind, pattern in _DBS_ACCOUNT if (m := pattern.search(text))), None
    )
    if found is None:
        return None
    kind, m = found
    groups = m.groupdict()
    if groups.get("date"):
        when = datetime.strptime(f"{groups['date']} {groups['time']}", "%d %b %Y %H:%M")
    else:
        when = _with_year(groups["day"], groups["time"], received)
    return CardAlert(
        bank="DBS",
        last4=m["last4"],
        when=when,
        currency=groups.get("currency") or "SGD",
        amount=Decimal(m["amount"].replace(",", "")),
        merchant=m["merchant"].strip(),
        message_id=message_id,
        kind=kind,
    )


def _citi(text: str, message_id: str, received: datetime | None) -> CardAlert | None:
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


def _uob(text: str, message_id: str, received: datetime | None) -> CardAlert | None:
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


def _ocbc(text: str, message_id: str, received: datetime | None) -> CardAlert | None:
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


def _clock(time: str, ampm: str | None) -> tuple[int, int]:
    hour, minute = (int(x) for x in re.split(r"[:.]", time))
    if ampm and ampm.upper() == "PM" and hour < 12:
        hour += 12
    elif ampm and ampm.upper() == "AM" and hour == 12:
        hour = 0
    return hour, minute


def _ocbc_account(text: str, message_id: str, received: datetime | None) -> CardAlert | None:
    found = next(
        ((kind, m) for kind, pattern in _OCBC_ACCOUNT if (m := pattern.search(text))), None
    )
    if found is None:
        return None
    kind, m = found
    groups = m.groupdict()
    if groups.get("numdate"):
        when = datetime.strptime(groups["numdate"], "%d/%m/%Y")
    else:
        if groups.get("date"):
            day = datetime.strptime(groups["date"], "%d %b %Y")
        elif received is not None:
            day = received
        else:
            raise CardAlertError("OCBC deposit alert without a date")
        hour, minute = _clock(groups["time"], groups["ampm"])
        when = datetime(day.year, day.month, day.day, hour, minute)
    if groups.get("srs") is not None:
        payee = "SRS contribution"
    elif groups.get("withdrawal") is not None:
        payee = "Withdrawal"
    else:
        payee = groups["merchant"].strip()
        note = (groups.get("note") or "").strip()
        if note and note.upper() != "OTHR":
            payee = f"{payee} ({note})"
    return CardAlert(
        bank="OCBC",
        last4=m["last4"],
        when=when,
        currency=m["currency"],
        amount=Decimal(m["amount"].replace(",", "")),
        merchant=payee,
        message_id=message_id,
        kind=kind,
    )


@dataclass(frozen=True)
class AlertSource:
    """Where a bank's alerts come from and how to read them."""

    bank: str
    sender: str
    # Subjects of alerts that must parse; anything else from the sender is ignored.
    subject: re.Pattern[str]
    # (text, message_id, arrival time in Singapore) -> alert
    parse: Callable[[str, str, datetime | None], CardAlert | None]


SOURCES = [
    AlertSource(
        "HSBC",
        "HSBC.Bank.Singapore.Limited@notification.hsbc.com.hk",
        re.compile(r"^Transaction Alerts\s+\(Credit Card\)$"),
        _hsbc,
    ),
    AlertSource(
        "DBS",
        "ibanking.alert@dbs.com",
        re.compile(
            r"^(Card Transaction Alert|digibank Alerts? - (You['’]ve received a transfer"
            r"|Successful bill payment|Successful NETS Scan & Pay))$"
        ),
        _dbs,
    ),
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
    AlertSource(
        "OCBC",
        "notifications@ocbc.com",
        re.compile(
            r"^(PayNow transfer made|NETS QR payment made|You have sent money to .+ via PayNow"
            r"|We have processed your funds transfer request"
            r"|OCBC Alert: (Money has been deposited in|Deposit in) your account"
            r"|OCBC Alert Withdrawal Made|OCBC Alert: Your request to make an SRS contribution)"
        ),
        _ocbc_account,
    ),
]


def parse_card_alert(
    source: AlertSource,
    subject: str,
    body_html: str,
    message_id: str,
    received_at: str | None = None,
) -> CardAlert | None:
    """Parse one email from a bank's alert sender.

    `received_at` is the email's UTC arrival time (ISO 8601), for templates
    that leave out the date. Returns None for emails that are not
    transaction alerts (statements, marketing). Raises CardAlertError when a
    transaction alert does not match the known template, so a template
    change (or a refund template not seen yet) fails loudly instead of
    silently dropping spend.
    """
    if not source.subject.search(subject.strip()):
        return None
    received = None
    if received_at:
        utc = datetime.fromisoformat(received_at.replace("Z", "+00:00"))
        received = (utc + timedelta(hours=8)).replace(tzinfo=None)
    alert = source.parse(html_to_text(body_html), message_id, received)
    if alert is None:
        raise CardAlertError(f"unrecognised {source.bank} card alert: {subject!r}")
    return alert


def clean_merchant(merchant: str) -> str:
    """Drop the "SINGAPORE SGP" / "SG SGP" suffix domestic merchants carry."""
    return _DOMESTIC_SUFFIX.sub("", merchant)


def to_transaction(alert: CardAlert, account: str) -> Transaction:
    """An alert as a Lunch Money transaction dated on the transaction date.

    A charge is an expense; a reversal or deposit is a credit.
    """
    payee = clean_merchant(alert.merchant)
    if alert.kind == "reversal":
        payee = f"Reversed: {payee}"
    return Transaction(
        date=alert.when.date(),
        description=payee,
        amount=-alert.amount if alert.kind == "spend" else alert.amount,
        account=account,
        original_currency=alert.currency,
        reference=alert.external_id,
    )


@dataclass
class AlertBatch:
    """A source's alerts, with each reversal paired to the charge it voids."""

    charges: list[CardAlert]  # charges no reversal voids, and deposits
    # (charge, reversal) pairs. Upload neither if the charge is not in Lunch
    # Money yet; upload the reversal as a credit if the charge went up earlier.
    voided: list[tuple[CardAlert, CardAlert]]
    # Reversals of holds that never sent a charge alert; nothing to undo.
    unmatched_reversals: list[CardAlert]


def pair_reversals(alerts: list[CardAlert]) -> AlertBatch:
    """Pair each reversal with the earliest unvoided charge it matches."""
    alerts = sorted(alerts, key=lambda a: (a.when, a.message_id))
    charges = [a for a in alerts if a.kind != "reversal"]
    voided: list[tuple[CardAlert, CardAlert]] = []
    unmatched: list[CardAlert] = []
    for reversal in (a for a in alerts if a.kind == "reversal"):
        match = next(
            (c for c in charges if c.kind == "spend" and c.charge_key == reversal.charge_key), None
        )
        if match is None:
            unmatched.append(reversal)
            continue
        charges.remove(match)
        voided.append((match, reversal))
    return AlertBatch(charges=charges, voided=voided, unmatched_reversals=unmatched)
