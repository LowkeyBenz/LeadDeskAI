import csv
from pathlib import Path

import pytest

from leaddesk_ai.db.repository import Repository


def create_lead(repo: Repository, tmp_path: Path) -> int:
    path = tmp_path / "lead.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["owner_name", "property_address", "property_city", "property_state", "property_zip"])
        writer.writeheader()
        writer.writerow({"owner_name": "Taylor Seller", "property_address": "88 Market St", "property_city": "Phoenix", "property_state": "AZ", "property_zip": "85001"})
    repo.import_leads_csv(path)
    return int(repo.list_properties()[0]["id"])


def test_save_and_load_seller_profile(tmp_path):
    repo = Repository(tmp_path / "seller.db")
    property_id = create_lead(repo, tmp_path)
    repo.save_seller_profile(
        property_id,
        motivation_level=8,
        occupancy="Vacant",
        timeline="30 days",
        preferred_contact="Phone",
        tags="vacant, inherited",
        asking_price=125000,
        reason_for_selling="Inherited property",
        marketing_source="Direct Mail",
    )
    profile = repo.seller_profile(property_id)
    details = repo.property_details(property_id)
    assert profile["motivation_level"] == 8
    assert profile["occupancy"] == "Vacant"
    assert profile["asking_price"] == 125000
    assert details["marketing_source"] == "Direct Mail"
    repo.close()


def test_seller_profile_validation(tmp_path):
    repo = Repository(tmp_path / "validation.db")
    property_id = create_lead(repo, tmp_path)
    with pytest.raises(ValueError, match="between 0 and 10"):
        repo.save_seller_profile(property_id, motivation_level=11)
    with pytest.raises(ValueError, match="cannot be negative"):
        repo.save_seller_profile(property_id, asking_price=-1)
    repo.close()


def test_communication_updates_follow_up_queue(tmp_path):
    repo = Repository(tmp_path / "communications.db")
    property_id = create_lead(repo, tmp_path)
    communication_id = repo.add_communication(
        property_id,
        channel="Call",
        outcome="Interested",
        notes="Call again after spouse reviews",
        contacted_at="2026-07-18T14:30:00",
        next_follow_up_date="2026-07-20",
    )
    rows = repo.list_communications(property_id)
    queue = repo.follow_up_queue()
    assert rows[0]["id"] == communication_id
    assert rows[0]["outcome"] == "Interested"
    assert queue[0]["id"] == property_id
    assert queue[0]["follow_up_date"] == "2026-07-20"
    assert repo.property_details(property_id)["status"] == "Follow-Up"
    repo.close()


def test_invalid_communication_date(tmp_path):
    repo = Repository(tmp_path / "dates.db")
    property_id = create_lead(repo, tmp_path)
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        repo.add_communication(property_id, channel="Text", next_follow_up_date="07/20/2026")
    repo.close()
