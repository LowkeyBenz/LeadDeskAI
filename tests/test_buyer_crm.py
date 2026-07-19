from pathlib import Path

import pytest

from leaddesk_ai.db.repository import Repository


def create_property(repo: Repository) -> int:
    stamp = "2026-07-19T00:00:00"
    with repo.conn:
        cur = repo.conn.execute(
            """INSERT INTO properties(address,city,state,zip,county,property_type,status,priority,created_at,updated_at)
            VALUES('123 Main St','Phoenix','AZ','85001','Maricopa','Single Family','New','Normal',?,?)""",
            (stamp, stamp),
        )
        property_id = int(cur.lastrowid)
        owner = repo.conn.execute(
            "INSERT INTO owners(property_id,name,created_at) VALUES(?,?,?)",
            (property_id, "Seller", stamp),
        )
        repo.conn.execute("INSERT INTO communication_preferences(property_id,updated_at) VALUES(?,?)", (property_id, stamp))
    return property_id


def test_create_update_and_search_buyer(tmp_path: Path):
    repo = Repository(tmp_path / "test.db")
    buyer_id = repo.save_buyer({
        "name": "Phoenix Cash Buyer",
        "company": "Desert Homes LLC",
        "phone": "555-0100",
        "markets": "AZ",
        "counties": "Maricopa",
        "zip_codes": "85001",
        "property_types": "Single Family",
        "min_price": 50000,
        "max_price": 250000,
        "funding_type": "Cash",
        "avg_close_days": 14,
        "active": True,
    })
    assert repo.stats()["buyers"] == 1
    assert repo.list_buyers("Desert")[0]["id"] == buyer_id
    repo.save_buyer({"name": "Phoenix Buyer Updated", "active": True}, buyer_id)
    assert repo.buyer(buyer_id)["name"] == "Phoenix Buyer Updated"
    repo.close()


def test_buyer_matching_and_offer_pipeline(tmp_path: Path):
    repo = Repository(tmp_path / "test.db")
    property_id = create_property(repo)
    buyer_id = repo.save_buyer({
        "name": "Maricopa Buyer",
        "markets": "AZ",
        "counties": "Maricopa",
        "zip_codes": "85001",
        "property_types": "Single Family",
        "min_price": 50000,
        "max_price": 250000,
        "funding_type": "Cash",
        "avg_close_days": 10,
        "active": True,
    })
    repo.save_deal_analysis(property_id, arv=300000, purchase_price=140000, repairs=50000, wholesale_fee=10000, target_pct=70)
    matches = repo.match_buyers(property_id)
    assert matches[0]["id"] == buyer_id
    assert matches[0]["match_label"] == "Strong"
    offer_id = repo.add_buyer_offer(property_id, buyer_id, 160000, "Interested", True, "Can close fast", "2026-07-19", "2026-07-20")
    offers = repo.list_buyer_offers(property_id)
    assert offers[0]["id"] == offer_id
    assert offers[0]["buyer_name"] == "Maricopa Buyer"
    assert offers[0]["status"] == "Interested"
    assert offers[0]["proof_of_funds"] == 1
    repo.close()


def test_buyer_validation_and_schema_upgrade(tmp_path: Path):
    repo = Repository(tmp_path / "test.db")
    with pytest.raises(ValueError, match="Buyer name"):
        repo.save_buyer({"name": ""})
    with pytest.raises(ValueError, match="Minimum price"):
        repo.save_buyer({"name": "Bad Buy Box", "min_price": 200000, "max_price": 100000})
    columns = {row["name"] for row in repo.conn.execute("PRAGMA table_info(buyer_offers)")}
    assert {"sent_date", "responded_date"} <= columns
    repo.close()
