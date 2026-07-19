from datetime import date

from leaddesk_ai.services.ai_engine import (
    analyze_property,
    calculate_opportunity_score,
    calculate_priority,
)


def strong_property():
    return {
        "address": "123 Main St",
        "city": "Phoenix",
        "state": "AZ",
        "status": "Under Contract",
        "priority": "High",
        "motivation_level": 9,
        "phone": "555-0100",
        "arv": 250000,
        "mao": 135000,
        "projected_profit": 30000,
        "deal_score": "Excellent",
        "buyer_match_count": 6,
        "selected_comp_count": 3,
        "follow_up_date": "2026-07-18",
    }


def test_priority_thresholds():
    assert calculate_priority(90) == "Urgent"
    assert calculate_priority(70) == "High"
    assert calculate_priority(50) == "Medium"
    assert calculate_priority(20) == "Low"


def test_strong_property_scores_high():
    score = calculate_opportunity_score(strong_property(), today=date(2026, 7, 18))
    assert 80 <= score <= 100


def test_restricted_missing_contact_reduces_score_and_creates_risks():
    data = {
        "address": "10 Risk Rd",
        "status": "New",
        "motivation_level": 0,
        "internal_dnc": True,
        "selected_comp_count": 0,
    }
    result = analyze_property(data, today=date(2026, 7, 18))
    assert result.score < 40
    assert result.priority == "Low"
    assert any("restricted" in risk.lower() for risk in result.risks)
    assert any("no phone" in risk.lower() for risk in result.risks)
    assert "Review contact permissions" in result.next_actions[0]


def test_overdue_follow_up_is_flagged():
    data = strong_property()
    data["follow_up_date"] = "2026-07-10"
    result = analyze_property(data, today=date(2026, 7, 18))
    assert any("overdue" in risk.lower() for risk in result.risks)
    assert any("follow-up today" in action.lower() for action in result.next_actions)


def test_summary_contains_key_deal_numbers():
    result = analyze_property(strong_property(), today=date(2026, 7, 18))
    assert "123 Main St" in result.summary
    assert "250,000" in result.summary
    assert "135,000" in result.summary
    assert result.to_dict()["score"] == result.score
