"""Rule-based property insights for LeadDesk AI.

This module intentionally has no network or API dependency. It turns existing
CRM data into a consistent opportunity score, concise summary, risks, strengths,
and suggested next actions. A future external AI provider can consume the same
``PropertyInsight`` result without changing the rest of the application.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any, Mapping


@dataclass(frozen=True)
class PropertyInsight:
    """Structured result returned by :func:`analyze_property`."""

    score: int
    priority: str
    summary: str
    strengths: tuple[str, ...]
    risks: tuple[str, ...]
    next_actions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly dictionary."""
        result = asdict(self)
        result["strengths"] = list(self.strengths)
        result["risks"] = list(self.risks)
        result["next_actions"] = list(self.next_actions)
        return result


def _value(data: Mapping[str, Any], key: str, default: Any = None) -> Any:
    value = data.get(key, default)
    return default if value is None else value


def _text(data: Mapping[str, Any], key: str) -> str:
    return str(_value(data, key, "") or "").strip()


def _number(data: Mapping[str, Any], key: str) -> float:
    value = _value(data, key, 0)
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _integer(data: Mapping[str, Any], key: str) -> int:
    try:
        return int(float(_value(data, key, 0) or 0))
    except (TypeError, ValueError):
        return 0


def _parse_date(value: str) -> date | None:
    value = value.strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def calculate_priority(score: int) -> str:
    """Translate a 0–100 opportunity score into a business priority."""
    score = max(0, min(100, int(score)))
    if score >= 80:
        return "Urgent"
    if score >= 65:
        return "High"
    if score >= 40:
        return "Medium"
    return "Low"


def calculate_opportunity_score(data: Mapping[str, Any], *, today: date | None = None) -> int:
    """Calculate a deterministic opportunity score from existing CRM data.

    Expected keys are intentionally flat so callers can pass a ``dict`` or a
    SQLite row converted to a dictionary. Missing data is handled safely.
    """
    today = today or date.today()
    score = 15

    motivation = max(0, min(10, _integer(data, "motivation_level")))
    score += motivation * 3

    priority = _text(data, "priority").lower()
    score += {"urgent": 15, "high": 10, "normal": 5, "medium": 5}.get(priority, 0)

    status = _text(data, "status").lower()
    score += {
        "contacted": 4,
        "follow-up": 7,
        "offer made": 10,
        "under contract": 15,
        "closed": 5,
        "dead": -30,
    }.get(status, 0)

    projected_profit = _number(data, "projected_profit")
    if projected_profit >= 30000:
        score += 15
    elif projected_profit >= 15000:
        score += 10
    elif projected_profit > 0:
        score += 5

    deal_score = _text(data, "deal_score").lower()
    score += {"excellent": 10, "good": 6, "marginal": 2, "bad": -8}.get(deal_score, 0)

    buyer_matches = max(0, _integer(data, "buyer_match_count"))
    score += min(10, buyer_matches * 2)

    selected_comps = max(0, _integer(data, "selected_comp_count"))
    if selected_comps >= 3:
        score += 5
    elif selected_comps > 0:
        score += 2

    follow_up = _parse_date(_text(data, "follow_up_date"))
    if follow_up:
        if follow_up < today:
            score += 8
        elif follow_up == today:
            score += 6
        elif (follow_up - today).days <= 3:
            score += 3

    if bool(_value(data, "internal_dnc", False)) or bool(_value(data, "opt_out", False)):
        score -= 15

    if not _text(data, "phone") and not _text(data, "email"):
        score -= 8

    return max(0, min(100, int(round(score))))


def identify_strengths(data: Mapping[str, Any]) -> tuple[str, ...]:
    strengths: list[str] = []
    motivation = _integer(data, "motivation_level")
    if motivation >= 8:
        strengths.append(f"Seller motivation is strong ({motivation}/10).")
    elif motivation >= 5:
        strengths.append(f"Seller shows moderate motivation ({motivation}/10).")

    profit = _number(data, "projected_profit")
    if profit >= 30000:
        strengths.append(f"Projected profit is strong (${profit:,.0f}).")
    elif profit >= 15000:
        strengths.append(f"Projected profit is workable (${profit:,.0f}).")

    matches = _integer(data, "buyer_match_count")
    if matches >= 5:
        strengths.append(f"There are {matches} matching buyers.")
    elif matches > 0:
        strengths.append(f"There are {matches} potential buyer matches.")

    comps = _integer(data, "selected_comp_count")
    if comps >= 3:
        strengths.append(f"ARV is supported by {comps} selected comparable sales.")

    if _text(data, "status") in {"Offer Made", "Under Contract"}:
        strengths.append(f"The lead has advanced to {_text(data, 'status')}." )

    return tuple(strengths)


def identify_risks(data: Mapping[str, Any], *, today: date | None = None) -> tuple[str, ...]:
    today = today or date.today()
    risks: list[str] = []

    if bool(_value(data, "internal_dnc", False)) or bool(_value(data, "opt_out", False)):
        risks.append("Contact is restricted; review permissions before outreach.")
    if not _text(data, "phone") and not _text(data, "email"):
        risks.append("No phone number or email is saved.")
    if _integer(data, "motivation_level") == 0:
        risks.append("Seller motivation has not been assessed.")
    if _integer(data, "selected_comp_count") < 3:
        risks.append("Fewer than three selected comps support the ARV.")
    if _number(data, "arv") <= 0:
        risks.append("No ARV has been saved in the latest deal analysis.")
    if _number(data, "projected_profit") < 10000 and _number(data, "arv") > 0:
        risks.append("Projected profit is below $10,000.")

    follow_up = _parse_date(_text(data, "follow_up_date"))
    if follow_up and follow_up < today:
        risks.append(f"Follow-up is overdue since {follow_up.isoformat()}.")
    elif not follow_up and _text(data, "status") not in {"Closed", "Dead"}:
        risks.append("No follow-up date is scheduled.")

    return tuple(risks)


def recommend_next_actions(data: Mapping[str, Any], *, today: date | None = None) -> tuple[str, ...]:
    today = today or date.today()
    actions: list[str] = []
    restricted = bool(_value(data, "internal_dnc", False)) or bool(_value(data, "opt_out", False))
    status = _text(data, "status") or "New"
    follow_up = _parse_date(_text(data, "follow_up_date"))

    if restricted:
        actions.append("Review contact permissions and use only an allowed outreach method.")
    elif not _text(data, "phone") and not _text(data, "email"):
        actions.append("Find and verify a lawful contact method for the owner.")
    elif follow_up and follow_up <= today:
        actions.append("Complete the scheduled seller follow-up today.")
    elif status == "New":
        actions.append("Make the first seller contact and record the outcome.")

    if _integer(data, "motivation_level") == 0:
        actions.append("Ask the seller about motivation, timeline, occupancy, and asking price.")
    if _integer(data, "selected_comp_count") < 3:
        actions.append("Add and verify at least three comparable sales.")
    if _number(data, "arv") <= 0:
        actions.append("Complete a deal analysis with ARV and repair estimates.")
    elif status in {"Contacted", "Follow-Up"} and _number(data, "mao") > 0:
        actions.append(f"Prepare or review an offer near the saved MAO of ${_number(data, 'mao'):,.0f}.")

    matches = _integer(data, "buyer_match_count")
    if status in {"Offer Made", "Under Contract"} and matches == 0:
        actions.append("Add buyer criteria or find matching cash buyers.")
    elif status == "Under Contract" and matches > 0:
        actions.append(f"Send the deal to the top {min(matches, 5)} matching buyers.")

    if not actions:
        actions.append("Review the activity timeline and schedule the next concrete step.")

    return tuple(actions[:5])


def generate_summary(data: Mapping[str, Any], score: int | None = None) -> str:
    score = calculate_opportunity_score(data) if score is None else score
    address = _text(data, "address") or "Unnamed property"
    city = _text(data, "city")
    state = _text(data, "state")
    location = ", ".join(part for part in (city, state) if part)
    status = _text(data, "status") or "New"
    motivation = _integer(data, "motivation_level")
    arv = _number(data, "arv")
    mao = _number(data, "mao")
    profit = _number(data, "projected_profit")

    lines = [f"{address}{' — ' + location if location else ''}", f"Status: {status}; Opportunity score: {score}/100 ({calculate_priority(score)})."]
    if motivation:
        lines.append(f"Seller motivation: {motivation}/10.")
    if arv > 0:
        deal_line = f"Latest analysis: ARV ${arv:,.0f}"
        if mao > 0:
            deal_line += f", MAO ${mao:,.0f}"
        if profit:
            deal_line += f", projected profit ${profit:,.0f}"
        lines.append(deal_line + ".")
    return "\n".join(lines)


def analyze_property(data: Mapping[str, Any], *, today: date | None = None) -> PropertyInsight:
    """Return all rule-based insights for one property."""
    score = calculate_opportunity_score(data, today=today)
    return PropertyInsight(
        score=score,
        priority=calculate_priority(score),
        summary=generate_summary(data, score=score),
        strengths=identify_strengths(data),
        risks=identify_risks(data, today=today),
        next_actions=recommend_next_actions(data, today=today),
    )
