"""CLI batch: locked seeds offline, generated ids need --llm, one bad row does not stop the file."""

from __future__ import annotations

from intake_triage.batch import lookup_record, process_batch, process_row
from intake_triage.cli import main


def test_lookup_locked_seed():
    row = lookup_record("HG-2026-0011")
    assert row["company_name"]
    result = process_row(row)
    assert result["decision"]["abstained"] is True
    assert result["enquiry_id"] == "HG-2026-0011"


def test_lookup_missing():
    try:
        lookup_record("HG-NOPE")
    except KeyError as exc:
        assert "HG-NOPE" in str(exc)
    else:
        raise AssertionError("expected KeyError")


def test_batch_isolates_bad_row():
    good = lookup_record("HG-2026-0001")
    bad = {**good, "enquiry_id": "HG-BAD-0001", "industry": "not-a-real-industry"}
    later = lookup_record("HG-2026-0002")
    result = process_batch([bad, good, later])
    assert result["summary"]["n"] == 3
    assert result["results"][0]["error"]
    assert result["results"][0]["decision"]["abstained"] is True
    assert result["results"][1]["decision"]["abstained"] is False
    assert result["results"][1]["decision"]["service_line"] == "TAX_STRUCTURING"
    assert result["results"][2]["enquiry_id"] == "HG-2026-0002"


def test_cli_run_id(capsys):
    assert main(["run", "--id", "HG-2026-0011"]) == 0
    out = capsys.readouterr().out
    assert "HG-2026-0011" in out
    assert "abstained=True" in out


def test_cli_unknown_id(capsys):
    assert main(["run", "--id", "HG-NOPE"]) == 1
    assert "HG-NOPE" in capsys.readouterr().out


def test_cli_explain():
    assert main(["generate", "--explain"]) == 0


def test_intake_csv_row_uses_locked_seed_offline():
    row = lookup_record("HG-2026-0001")
    row.pop("extraction_json", None)
    result = process_row(row)
    assert result["extraction_source"] == "authored_drivers"
    assert result["decision"]["service_line"] == "TAX_STRUCTURING"


def test_unknown_intake_row_offline_abstains():
    row = {
        "enquiry_id": "HG-2026-0999",
        "submitted_at": "2026-04-01T09:00:00Z",
        "contact_name": "",
        "contact_email": "",
        "company_name": "Walk-in Ltd",
        "industry": "other",
        "company_size": "sme",
        "urgency": "normal",
        "description": "Need a review of a corporation-tax issue. One UK company.",
    }
    result = process_row(row)
    assert result["extraction_source"] == "empty"
    assert result["decision"]["abstained"] is True
    assert result["error"]
