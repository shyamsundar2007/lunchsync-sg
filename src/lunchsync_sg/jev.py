"""JEV client for classifying Lunch Money transactions."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import requests

CATEGORY_GUIDANCE: dict[str, str] = {
    "Payment, Transfer": (
        "Internal account movement, credit-card payment, balance transfer, or money movement "
        "that is neither spending nor investing."
    ),
    "Liquid Investments": (
        "Brokerage, cryptocurrency, or movement into or out of liquid investments."
    ),
    "Tax advantaged investments": (
        "CPF, SRS, retirement, or another tax-advantaged investment contribution."
    ),
    "Restaurants": "Local restaurant, cafe, or takeaway that is not specifically a work meal.",
    "Work food": "Meal bought at or for work, including a workplace lunch.",
    "Groceries": "Supermarket, produce, or food bought for home preparation.",
    "Essentials": (
        "Necessary household or personal purchase that is not groceries, utilities, healthcare, "
        "or transport."
    ),
    "Splurging": "Discretionary shopping for oneself; a nonessential retail purchase.",
    "Gifts": "Purchase or transfer intended as a gift for someone else.",
    "Public Transport": "Local bus, MRT, SimplyGo, or public transit.",
    "Cab": "Local taxi or ride-hail; exclude overseas transport and vehicle rental.",
    "Rental": "Vehicle rental or car-sharing rental; exclude taxi rides.",
    "Transport - travel": "Taxi, ride-hail, transit, or local transportation while travelling.",
    "Meals - travel": "Restaurant, cafe, groceries, or meal while travelling.",
    "Flight - travel": "Airfare, airline fees, and flight-related purchases.",
    "Hotel - travel": "Hotel, Airbnb, and other lodging while travelling.",
    "Misc - travel": "Trip expense not fitting flight, hotel, meals, transport, or sightseeing.",
    "Sightseeing - travel": "Tourist attractions, admissions, tours, and sightseeing on a trip.",
    "Work": "Professional tools, subscriptions, and employee work expenses; never salary income.",
    "Business": "Company administration and business expenses such as registration or hosting.",
    "Interest": "Bank interest received.",
    "Salary": "Employment salary or wages received.",
    "Refund": "Returned money reversing an earlier expense; not salary or an ordinary transfer.",
    "Sale": "Money received from selling goods or services.",
    "Other income": (
        "Incoming money that is not salary, interest, dividends, rent, refund, or sale."
    ),
    "Bank Fees": "Card or bank fees, annual fees, late charges, and FX conversion fees.",
    "Income Tax": "Personal income tax payment or tax preparation expense.",
    "Medical": "Doctor, dentist, clinic, medicine, or medical treatment.",
    "Paying for others": "Expense paid on behalf of another person and separated from own spending.",
}


@dataclass(frozen=True)
class CategorizationDecision:
    """A category decision returned by JEV."""

    category_id: int | None
    confidence: float


def _direction(amount: Any) -> str:
    """Convert a Lunch Money amount into a human-readable direction."""
    try:
        value = Decimal(str(amount))
    except (InvalidOperation, TypeError, ValueError):
        return "unknown"
    if value < 0:
        return "outgoing"
    if value > 0:
        return "incoming"
    return "zero"


def _category_criteria(categories: list[dict[str, Any]]) -> dict[str, str]:
    """Build JEV choice criteria keyed by assignable Lunch Money category ID."""
    criteria: dict[str, str] = {}
    for category in categories:
        category_id = str(category["id"])
        name = str(category["name"]).strip()
        group = str(category.get("group_category_name") or "").strip()
        description = str(category.get("description") or "").strip()

        label = f"{group} > {name}" if group else name
        details = description or CATEGORY_GUIDANCE.get(name)
        criteria[category_id] = f"{label}. {details}" if details else label

    criteria["unmatched"] = (
        "No existing active category is a reasonable fit; leave for manual review."
    )
    return criteria


class JevClient:
    """Client for TypeSafe's JEV System One API."""

    BASE_URL = "https://api.typesafe.ai/v1"
    MODEL = "jev-latest"

    def __init__(self, api_key: str) -> None:
        """Initialize a JEV client."""
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
        )

    def categorize(
        self,
        transaction: dict[str, Any],
        categories: list[dict[str, Any]],
    ) -> CategorizationDecision:
        """Choose an existing Lunch Money category for a transaction."""
        valid_ids = {int(category["id"]) for category in categories}
        state = {
            "transaction": {
                "date": transaction.get("date"),
                "raw_description": transaction.get("payee"),
                "amount": transaction.get("amount"),
                "direction": _direction(transaction.get("amount")),
                "currency": transaction.get("currency"),
                "account": (
                    transaction.get("account_display_name")
                    or transaction.get("asset_display_name")
                    or transaction.get("asset_name")
                ),
            }
        }
        questions = {
            "category": {
                "type": "choice",
                "instructions": (
                    "Choose the existing Lunch Money category matching the transaction's economic "
                    "purpose. Ignore bank transport wrappers such as FAST PAYMENT, OTHR, GIRO, "
                    "PayNow, and NETS; focus on the recipient, merchant, and purpose. Foreign "
                    "merchant locations or currencies indicate travel categories. Negative amounts "
                    "are outgoing and positive amounts incoming. Follow the explicit category "
                    "definitions. Choose unmatched when evidence is genuinely insufficient."
                ),
                "criteria": _category_criteria(categories),
            }
        }

        response = self._session.post(
            f"{self.BASE_URL}/systemone",
            json={"model": self.MODEL, "state": state, "questions": questions},
            timeout=45,
        )
        response.raise_for_status()
        answer = response.json()["answers"]["category"]

        choice = str(answer["choice"])
        confidence = float(answer["confidence"])
        if choice == "unmatched":
            return CategorizationDecision(category_id=None, confidence=confidence)

        try:
            category_id = int(choice)
        except ValueError:
            return CategorizationDecision(category_id=None, confidence=confidence)

        if category_id not in valid_ids:
            return CategorizationDecision(category_id=None, confidence=confidence)
        return CategorizationDecision(category_id=category_id, confidence=confidence)
