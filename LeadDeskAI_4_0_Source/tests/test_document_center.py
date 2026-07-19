from leaddesk_ai.db.repository import Repository


def make_property(repo):
    stamp = "2026-07-19T00:00:00"
    with repo.conn:
        cur = repo.conn.execute(
            "INSERT INTO properties(address,city,state,zip,status,priority,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
            ("123 Main St", "Phoenix", "AZ", "85001", "New", "Normal", stamp, stamp),
        )
    return int(cur.lastrowid)


def test_document_lifecycle(tmp_path):
    repo = Repository(tmp_path / "db.sqlite")
    property_id = make_property(repo)
    document_id = repo.add_document(property_id, name="Offer Sheet", document_type="Offer Sheet", file_path="C:/docs/offer.pdf")
    rows = repo.list_documents(property_id)
    assert rows[0]["id"] == document_id
    assert rows[0]["status"] == "Draft"
    repo.update_document_status(document_id, "Sent")
    assert repo.list_documents(property_id)[0]["status"] == "Sent"
    repo.delete_document(document_id)
    assert repo.list_documents(property_id) == []
    repo.close()


def test_document_validation(tmp_path):
    repo = Repository(tmp_path / "db.sqlite")
    property_id = make_property(repo)
    try:
        repo.add_document(property_id, name="", document_type="Other")
    except ValueError as exc:
        assert "required" in str(exc).lower()
    else:
        raise AssertionError("Expected ValueError")
    repo.close()
