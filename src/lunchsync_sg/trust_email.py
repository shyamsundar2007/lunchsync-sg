"""Parse Trust Bank card alert emails into transactions.

Trust has no statement export, but it emails an alert for every card
purchase, refund and cancelled purchase. Each alert becomes one
transaction; a cancellation voids the purchase it names.
"""

import hashlib
import html
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from lunchsync_sg.models import Transaction

TRUST_SENDER = "from_us@trustbank.sg"

AlertKind = Literal["spend", "refund", "cancel"]

_AMOUNT = r"(?P<currency>[A-Z]{3}) (?P<amount>[\d,]+\.\d{2})"
_WHEN = r"(?P<when>\d{1,2} \w{3} \d{4} \d{2}:\d{2}) ?SGT"
_APOS = "['’]"

_PATTERNS: list[tuple[AlertKind, re.Pattern[str]]] = [
    ("spend", re.compile(
        rf"You{_APOS}ve spent {_AMOUNT} at (?P<merchant>.+?) on {_WHEN} "
        r"with Freedom credit card\."
    )),
    ("cancel", re.compile(
        rf"We{_APOS}ve cancelled your purchase of {_AMOUNT} at (?P<merchant>.+?) on {_WHEN} "
        r"with Freedom credit card\."
    )),
    ("refund", re.compile(
        rf"We{_APOS}ve refunded {_AMOUNT} from (?P<merchant>.+?) to your Trust card on {_WHEN}\."
    )),
]

# Subjects of alerts that must parse; anything else from Trust is ignored.
_TRANSACTION_SUBJECT = re.compile(r"\bTransaction (successful|refunded|cancelled)\b", re.I)

# Trailing tokens on Visa merchant strings: country, city, store/terminal numbers.
_MERCHANT_NOISE = re.compile(r"^(SG|SINGAPORE|\d+)$", re.I)


class TrustAlertError(ValueError):
    """A transaction alert whose body no longer matches the known templates."""


@dataclass(frozen=True)
class TrustAlert:
    """One card alert email."""

    kind: AlertKind
    when: datetime  # Singapore time, as printed in the email
    currency: str
    amount: Decimal  # always positive
    merchant: str  # raw, whitespace-collapsed
    message_id: str

    @property
    def external_id(self) -> str:
        """Stable Lunch Money external_id (Message-IDs exceed its 75-char limit)."""
        return "trust:" + hashlib.sha256(self.message_id.encode()).hexdigest()[:40]

    @property
    def purchase_key(self) -> tuple[str, Decimal, str, datetime]:
        """Fields a cancellation shares with the purchase it voids."""
        return (self.currency, self.amount, self.merchant, self.when)


def html_to_text(body: str) -> str:
    """Flatten an HTML email body to one line of text."""
    body = re.sub(r"<!--.*?-->", " ", body, flags=re.S)
    body = re.sub(r"<(style|script)\b.*?</\1>", " ", body, flags=re.S | re.I)
    body = re.sub(r"<[^>]+>", " ", body)
    return re.sub(r"\s+", " ", html.unescape(body)).strip()


def parse_alert(subject: str, body_html: str, message_id: str) -> TrustAlert | None:
    """Parse one Trust email.

    Returns None for emails that are not card transaction alerts (PayNow,
    logins, statements, marketing). Raises TrustAlertError when a
    transaction alert does not match any known template, so a template
    change fails loudly instead of silently dropping spend.
    """
    text = html_to_text(body_html)
    for kind, pattern in _PATTERNS:
        if m := pattern.search(text):
            return TrustAlert(
                kind=kind,
                when=datetime.strptime(m["when"], "%d %b %Y %H:%M"),
                currency=m["currency"],
                amount=Decimal(m["amount"].replace(",", "")),
                merchant=m["merchant"].strip(),
                message_id=message_id,
            )
    if _TRANSACTION_SUBJECT.search(subject):
        raise TrustAlertError(f"unrecognised Trust transaction alert: {subject!r}")
    return None


def clean_merchant(merchant: str) -> str:
    """Drop trailing country/city/store-number tokens from a merchant string."""
    tokens = merchant.split()
    while len(tokens) > 1 and _MERCHANT_NOISE.match(tokens[-1]):
        tokens.pop()
    return " ".join(tokens)


def _to_transaction(alert: TrustAlert, account: str) -> Transaction:
    payee = clean_merchant(alert.merchant)
    if alert.kind == "spend":
        amount = -alert.amount
    else:
        amount = alert.amount
        if alert.kind == "cancel":
            payee = f"Cancelled: {payee}"
    return Transaction(
        date=alert.when.date(),
        description=payee,
        amount=amount,
        account=account,
        original_currency=alert.currency,
        reference=alert.external_id,
    )


@dataclass
class TrustBatch:
    """Transactions derived from a set of alerts."""

    transactions: list[Transaction]
    # (purchase, cancellation) pairs found in the same batch. Upload neither
    # if the purchase is not in Lunch Money yet; upload the cancellation as
    # a credit if the purchase already went up in an earlier run.
    voided: list[tuple[Transaction, Transaction]]


def build_batch(alerts: list[TrustAlert], account: str) -> TrustBatch:
    """Turn alerts into transactions, pairing each cancellation with its purchase."""
    alerts = sorted(alerts, key=lambda a: (a.when, a.message_id))
    open_spends = [a for a in alerts if a.kind == "spend"]
    voided: list[tuple[Transaction, Transaction]] = []
    voided_ids: set[str] = set()
    unpaired_cancels: list[TrustAlert] = []

    for cancel in (a for a in alerts if a.kind == "cancel"):
        match = next((s for s in open_spends if s.purchase_key == cancel.purchase_key), None)
        if match is None:
            # Purchase is older than the batch, so it was uploaded earlier.
            unpaired_cancels.append(cancel)
            continue
        open_spends.remove(match)
        voided_ids.add(match.message_id)
        voided.append((_to_transaction(match, account), _to_transaction(cancel, account)))

    live = [
        a for a in alerts
        if (a.kind == "spend" and a.message_id not in voided_ids) or a.kind == "refund"
    ] + unpaired_cancels
    live.sort(key=lambda a: (a.when, a.message_id))
    return TrustBatch(transactions=[_to_transaction(a, account) for a in live], voided=voided)
