"""The failsafe exists so no enquiry is lost. These tests are about loss, not accuracy."""

from __future__ import annotations

import json

from intake_triage.batch import process_row
from intake_triage.failsafe import DECISION_LOG, REVIEW_DIR, failsafe_decision, fallback_enquiry, handle_failure
from intake_triage.policy_loader import load_policy
from intake_triage.schema import AbstainReason


def _row(**over) -> dict:
    row = {
        "enquiry_id": "HG-TEST-0001",
        "submitted_at": "2026-03-04T09:12:00Z",
        "contact_name": "Test Person",
        "contact_email": "test@example.example",
        "company_name": "Test Ltd",
        "industry": "professional_services",
        "company_size": "sme",
        "urgency": "normal",
        "description": "We need help with a UK corporation-tax question.",
        "difficulty": "easy",
        "split": "call",
        "hard_case_type": "",
    }
    row.update(over)
    return row


def test_failure_routes_to_the_analyst_not_a_lead():
    policy = load_policy()
    enquiry = fallback_enquiry(_row(), "boom")
    decision = failsafe_decision(enquiry, RuntimeError("API down"), policy)
    assert decision.abstained is True
    assert decision.route_to == policy["analyst_email"]
    assert decision.service_line is None
    assert decision.estimated_hours is None


def test_failure_is_extraction_failed_not_low_evidence():
    """An outage and a terse letter must never look the same in the queue."""
    enquiry = fallback_enquiry(_row(), "boom")
    decision = failsafe_decision(enquiry, RuntimeError("API down"))
    assert decision.abstain_reason is AbstainReason.EXTRACTION_FAILED
    assert decision.abstain_reason is not AbstainReason.LOW_EVIDENCE


def test_failure_names_the_cause_in_the_trace():
    enquiry = fallback_enquiry(_row(), "boom")
    decision = failsafe_decision(enquiry, RuntimeError("API down"))
    joined = " ".join(decision.rule_trace)
    assert "FAILSAFE" in joined
    assert "RuntimeError" in joined
    assert "API down" in joined


def test_failure_writes_an_email_and_a_json_for_review(tmp_path):
    review = tmp_path / "review"
    log = tmp_path / "decisions.jsonl"
    enquiry, decision, written = handle_failure(
        _row(), RuntimeError("API down"), review_dir=review, log_path=log
    )
    email_path = review / f"{enquiry.enquiry_id}.email.txt"
    json_path = review / f"{enquiry.enquiry_id}.json"
    assert email_path.exists() and json_path.exists()
    body = email_path.read_text(encoding="utf-8")
    # A failure email must not read like an ordinary abstention. It says the system
    # failed and asks for manual triage rather than offering candidates to pick from.
    assert "NOT TRIAGED" in body
    assert "Reply 1 or 2" not in body
    assert "API down" in body
    assert json.loads(json_path.read_text(encoding="utf-8"))["abstained"] is True
    assert log.exists() and log.read_text(encoding="utf-8").strip()
    assert written["email"] and written["json"]


def test_the_letter_survives_an_unparseable_row():
    """Every structured field is junk. The description still reaches the human."""
    letter = "Our board needs a view on the operating model before September."
    enquiry = fallback_enquiry(
        {"enquiry_id": "HG-BAD-0001", "description": letter}, "bad industry"
    )
    assert enquiry.description == letter
    assert enquiry.enquiry_id == "HG-BAD-0001"


def test_unparseable_row_still_produces_an_email_and_a_route():
    """Regression: this path used to return route_to None and an empty email body."""
    result = process_row(_row(industry="not_a_real_industry", company_size="enormous"))
    policy = load_policy()
    assert result["decision"]["abstained"] is True
    assert result["decision"]["route_to"] == policy["analyst_email"]
    assert result["email"].strip(), "an unparseable row must still generate an email"
    assert result["decision"]["abstain_reason"] == "extraction_failed"


def test_missing_api_key_abstains_instead_of_raising(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = process_row(_row(), use_llm=True)
    assert result["decision"]["abstained"] is True
    assert result["decision"]["abstain_reason"] == "extraction_failed"
    assert result["decision"]["route_to"] == load_policy()["analyst_email"]
    assert result["email"].strip()


def test_emit_survives_an_unwritable_review_dir(tmp_path):
    """A disk problem must not swallow the enquiry the failsafe protects."""
    blocker = tmp_path / "review"
    blocker.write_text("not a directory", encoding="utf-8")
    _, decision, written = handle_failure(
        _row(), RuntimeError("API down"), review_dir=blocker, log_path=tmp_path / "d.jsonl"
    )
    assert decision.abstained is True
    assert "error" in written
    assert written["email_body"].strip()


def test_failsafe_defaults_live_under_data_out():
    """Oracle eval writes data/decisions.jsonl. Failsafe must not append test rows there."""
    assert "out" in DECISION_LOG.parts
    assert DECISION_LOG.name == "failsafe.jsonl"
    assert "out" in REVIEW_DIR.parts
