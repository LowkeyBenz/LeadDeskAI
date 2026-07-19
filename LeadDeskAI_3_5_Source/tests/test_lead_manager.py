import csv
from pathlib import Path

import pytest

from leaddesk_ai.db.repository import Repository


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_csv_import_and_duplicate_protection(tmp_path):
    repo = Repository(tmp_path / "leads.db")
    source = tmp_path / "leads.csv"
    rows = [{
        "owner_name": "Alex Seller",
        "property_address": "123 Main St",
        "property_city": "Phoenix",
        "property_state": "AZ",
        "property_zip": "85001",
        "phone": "555-0100",
        "email": "alex@example.com",
        "apn": "APN-1",
    }]
    write_csv(source, rows)
    first = repo.import_leads_csv(source)
    second = repo.import_leads_csv(source)
    assert first == {"added": 1, "skipped": 0, "failed": 0}
    assert second == {"added": 0, "skipped": 1, "failed": 0}
    lead = repo.list_properties("Alex")[0]
    assert lead["phone"] == "555-0100"
    assert lead["email"] == "alex@example.com"
    repo.close()


def test_workflow_update_and_restrictions(tmp_path):
    repo = Repository(tmp_path / "workflow.db")
    source = tmp_path / "lead.csv"
    write_csv(source, [{
        "owner_name": "Jamie Owner",
        "property_address": "9 Oak Ave",
        "property_city": "Mesa",
        "property_state": "AZ",
        "property_zip": "85201",
    }])
    repo.import_leads_csv(source)
    property_id = repo.list_properties()[0]["id"]
    repo.update_property_workflow(property_id, "Follow-Up", "High", "2026-08-01")
    repo.set_contact_restrictions(property_id, True, False)
    lead = repo.property_details(property_id)
    assert lead["status"] == "Follow-Up"
    assert lead["priority"] == "High"
    assert lead["follow_up_date"] == "2026-08-01"
    assert lead["internal_dnc"] == 1
    repo.close()


def test_invalid_follow_up_date_rejected(tmp_path):
    repo = Repository(tmp_path / "invalid.db")
    source = tmp_path / "lead.csv"
    write_csv(source, [{"property_address": "1 Test St", "property_city": "Tempe", "property_state": "AZ", "property_zip": "85281"}])
    repo.import_leads_csv(source)
    property_id = repo.list_properties()[0]["id"]
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        repo.update_property_workflow(property_id, "New", "Normal", "08/01/2026")
    repo.close()
