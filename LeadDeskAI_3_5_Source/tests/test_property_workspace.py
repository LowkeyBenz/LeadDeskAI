import csv
from pathlib import Path

import pytest

from leaddesk_ai.db.repository import Repository


def create_lead(repo: Repository, tmp_path: Path) -> int:
    path = tmp_path / "lead.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["owner_name", "property_address", "property_city", "property_state", "property_zip"])
        writer.writeheader()
        writer.writerow({"owner_name": "Original Owner", "property_address": "10 First St", "property_city": "Phoenix", "property_state": "AZ", "property_zip": "85001"})
    repo.import_leads_csv(path)
    return int(repo.list_properties()[0]["id"])


def test_property_profile_update(tmp_path):
    repo = Repository(tmp_path / "profile.db")
    property_id = create_lead(repo, tmp_path)
    repo.update_property_profile(
        property_id,
        address="22 Updated Ave",
        city="Mesa",
        state="AZ",
        zip_code="85201",
        county="Maricopa",
        apn="ABC-123",
        property_type="Single Family",
        owner_name="Updated Owner",
        mailing_address="PO Box 42",
        phone="555-1212",
        email="owner@example.com",
    )
    lead = repo.property_details(property_id)
    assert lead["address"] == "22 Updated Ave"
    assert lead["owner_name"] == "Updated Owner"
    assert lead["phone"] == "555-1212"
    assert lead["email"] == "owner@example.com"
    assert repo.activities(property_id)[0]["activity_type"] == "Profile Updated"
    repo.close()


def test_property_address_required(tmp_path):
    repo = Repository(tmp_path / "required.db")
    property_id = create_lead(repo, tmp_path)
    with pytest.raises(ValueError, match="address is required"):
        repo.update_property_profile(property_id, address="")
    repo.close()


def test_task_lifecycle(tmp_path):
    repo = Repository(tmp_path / "tasks.db")
    property_id = create_lead(repo, tmp_path)
    task_id = repo.add_task(property_id, "Call seller", "2026-08-02", "High")
    task = repo.list_tasks(property_id)[0]
    assert task["id"] == task_id
    assert task["status"] == "Open"
    repo.set_task_completed(task_id)
    assert repo.list_tasks(property_id)[0]["status"] == "Completed"
    repo.close()


def test_invalid_task_date(tmp_path):
    repo = Repository(tmp_path / "taskdate.db")
    property_id = create_lead(repo, tmp_path)
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        repo.add_task(property_id, "Call", "08/02/2026")
    repo.close()
