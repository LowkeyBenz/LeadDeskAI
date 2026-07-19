from pathlib import Path

import pytest

from leaddesk_ai.db.repository import Repository, now
from leaddesk_ai.services.calculations import estimate_arv


def add_property(repo: Repository, square_feet: float = 1500) -> int:
    stamp = now()
    cur = repo.conn.execute(
        "INSERT INTO properties(address,city,state,zip,square_feet,status,priority,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
        ("10 Main St", "Utica", "NY", "13501", square_feet, "New", "Normal", stamp, stamp),
    )
    repo.conn.commit()
    return int(cur.lastrowid)


def test_estimate_arv_uses_price_per_square_foot():
    result = estimate_arv([
        {"sold_price": 200000, "square_feet": 1000, "selected": 1},
        {"sold_price": 330000, "square_feet": 1500, "selected": 1},
    ], subject_square_feet=1200)
    assert result["comp_count"] == 2
    assert result["average_ppsf"] == 210
    assert result["suggested_arv"] == 252000
    assert result["low_arv"] == 200000
    assert result["high_arv"] == 330000


def test_estimate_arv_ignores_excluded_comps():
    result = estimate_arv([
        {"sold_price": 200000, "square_feet": 1000, "selected": 1},
        {"sold_price": 900000, "square_feet": 1000, "selected": 0},
    ], subject_square_feet=1000)
    assert result["comp_count"] == 1
    assert result["suggested_arv"] == 200000


def test_comparable_lifecycle_and_arv(tmp_path: Path):
    repo = Repository(tmp_path / "test.db")
    property_id = add_property(repo, 1200)
    comp_id = repo.add_comparable_sale(property_id, address="12 Oak St", sold_price=240000,
        sold_date="2026-06-01", square_feet=1200, bedrooms=3, bathrooms=2, distance_miles=.5,
        source="County records", verified=True)
    rows = repo.list_comparable_sales(property_id)
    assert rows[0]["id"] == comp_id
    assert rows[0]["bedrooms"] == 3
    assert repo.comparable_arv(property_id)["suggested_arv"] == 240000
    repo.set_comparable_selected(comp_id, False)
    with pytest.raises(ValueError, match="Select at least one"):
        repo.comparable_arv(property_id)
    repo.delete_comparable_sale(comp_id)
    assert repo.list_comparable_sales(property_id) == []
    repo.close()


def test_comparable_validation(tmp_path: Path):
    repo = Repository(tmp_path / "test.db")
    property_id = add_property(repo)
    with pytest.raises(ValueError, match="address"):
        repo.add_comparable_sale(property_id, address="", sold_price=100000)
    with pytest.raises(ValueError, match="greater than zero"):
        repo.add_comparable_sale(property_id, address="12 Oak", sold_price=0)
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        repo.add_comparable_sale(property_id, address="12 Oak", sold_price=100000, sold_date="06/01/2026")
    repo.close()


def test_save_offer_scenario(tmp_path: Path):
    repo = Repository(tmp_path / "test.db")
    property_id = add_property(repo)
    offer_id = repo.save_offer_scenario(property_id, suggested_arv=250000, seller_offer=130000,
        buyer_price=145000, assignment_fee=15000, notes="Initial offer")
    rows = repo.list_offer_scenarios(property_id)
    assert rows[0]["id"] == offer_id
    assert rows[0]["estimated_profit"] == 15000
    assert rows[0]["notes"] == "Initial offer"
    repo.close()
