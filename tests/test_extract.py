from __future__ import annotations

from copy import deepcopy

from intake_triage.extract import validate_evidence_spans
from intake_triage.generate import seed_to_enquiry, seed_to_extraction
from intake_triage.pipeline import triage_from_extraction
from intake_triage.schema import Driver, Extraction, WorkSignal
from intake_triage.seeds import SEEDS


def _seed(eid: str) -> dict:
    return next(s for s in SEEDS if s["enquiry_id"] == eid)


def test_rejected_span_drops_work_signal():
    source = "Need a UK tax review for one company."
    extraction = Extraction(
        work_signals=[
            Driver(value=WorkSignal.TAX, evidence_span="this span is not in the source"),
            Driver(value=WorkSignal.TRANSACTION, evidence_span="UK tax review"),
        ]
    )
    checked, rejected = validate_evidence_spans(extraction, source)
    assert "work_signals" in rejected
    values = [item.value for item in checked.work_signals]
    assert WorkSignal.TAX not in values
    assert WorkSignal.TRANSACTION in values


def test_missing_span_drops_value():
    source = "Need a UK tax review for one company."
    extraction = Extraction(
        work_signals=[Driver(value=WorkSignal.TAX, evidence_span=None)],
        systems_change=Driver(value=True, evidence_span=None),
    )
    checked, rejected = validate_evidence_spans(extraction, source)
    assert checked.work_signals == []
    assert checked.systems_change.value is None
    assert "work_signals" in rejected
    assert "systems_change" in rejected


def test_valid_span_kept():
    source = "Need a UK tax review for one company."
    extraction = Extraction(
        work_signals=[Driver(value=WorkSignal.TAX, evidence_span="UK tax review")],
    )
    checked, rejected = validate_evidence_spans(extraction, source)
    assert rejected == []
    assert checked.work_signals[0].value == WorkSignal.TAX


def test_null_systems_does_not_commit_simple_tax():
    seed = deepcopy(_seed("HG-2026-0001"))
    seed["extraction"]["systems_change"] = {"value": None, "evidence_span": None}
    enquiry = seed_to_enquiry(seed)
    extraction = seed_to_extraction(seed)
    decision = triage_from_extraction(enquiry, extraction)
    assert decision.abstained is True
    assert decision.estimated_hours is None
    assert decision.complexity is None
    assert decision.service_line is None
    assert decision.competing_lines or decision.rule_trace
    assert any("PROVISIONAL" in line for line in decision.rule_trace)
