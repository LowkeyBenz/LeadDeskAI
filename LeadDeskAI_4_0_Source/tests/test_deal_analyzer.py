from pathlib import Path

import pytest

from leaddesk_ai.db.repository import Repository, now
from leaddesk_ai.services.calculations import analyze_deal


def add_property(repo: Repository) -> int:
    stamp = now()
    cur = repo.conn.execute(
        "INSERT INTO properties(address,city,state,zip,status,priority,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
        ("10 Main St", "Utica", "NY", "13501", "New", "Normal", stamp, stamp),
    )
    repo.conn.commit()
    return int(cur.lastrowid)


def test_analyze_deal_calculates_summary():
    result = analyze_deal(arv=200000, purchase_price=100000, repairs=20000, closing_costs=5000, holding_costs=3000, marketing_costs=1000, misc_costs=1000, wholesale_fee=10000, target_pct=70)
    assert result["mao"] == 100000
    assert result["total_investment"] == 130000
    assert result["projected_profit"] == 10000
    assert result["roi"] == pytest.approx(7.69, abs=0.01)
    assert result["deal_score"] == "Marginal"


def test_analyze_deal_rejects_negative_values():
    with pytest.raises(ValueError):
        analyze_deal(arv=200000, purchase_price=-1)


def test_save_and_list_deal_analysis(tmp_path: Path):
    repo = Repository(tmp_path / "test.db")
    property_id = add_property(repo)
    deal_id = repo.save_deal_analysis(property_id, arv=250000, purchase_price=120000, repairs=25000, closing_costs=5000, holding_costs=3000, marketing_costs=1000, misc_costs=1000, wholesale_fee=15000, target_pct=70)
    rows = repo.list_deal_analyses(property_id)
    assert rows[0]["id"] == deal_id
    assert rows[0]["mao"] == 125000
    assert rows[0]["projected_profit"] == 20000
    assert rows[0]["deal_score"] == "Good"
    repo.close()


def test_save_deal_requires_property(tmp_path: Path):
    repo = Repository(tmp_path / "test.db")
    with pytest.raises(ValueError, match="Property not found"):
        repo.save_deal_analysis(999, arv=100000, purchase_price=50000)
    repo.close()
