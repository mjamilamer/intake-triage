"""Span validation, Sonnet pin, and Haiku Driver coerce."""

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


def test_pinned_model_is_sonnet():
    from intake_triage.extract import PINNED_MODEL

    assert PINNED_MODEL == "claude-sonnet-4-6"
    assert "latest" not in PINNED_MODEL


def test_extras_spans_are_in_the_letter():
    from intake_triage.extract import validate_evidence_spans
    from intake_triage.generate import seed_to_extraction
    from intake_triage.journal_extras import JOURNAL_EXTRAS

    for rec in JOURNAL_EXTRAS:
        _, rejected = validate_evidence_spans(seed_to_extraction(rec), rec["description"])
        assert rejected == [], f"{rec['enquiry_id']} rejected {rejected}"
        assert len(rec["description"]) > 40


def test_long_prompt_is_actually_long():
    from intake_triage.journal_extras import JOURNAL_EXTRAS, LONG_IDS

    for rec in JOURNAL_EXTRAS:
        if rec["enquiry_id"] in LONG_IDS:
            assert len(rec["description"]) > 900


def test_extract_create_kwargs_omit_temperature():
    import inspect

    from intake_triage.extract import extract_with_llm

    source = inspect.getsource(extract_with_llm)
    assert "temperature=" not in source


def test_coerce_bare_haiku_payload_from_0214():
    from intake_triage.extract import coerce_extraction_payload, validate_evidence_spans
    from intake_triage.schema import WorkSignal

    source = (
        "Writing for Harbor & Pine, a consumer business with about 180 people. UK only. This is "
        "not urgent. Board asked whether brand and operations should sit in separate teams. Want "
        "a view on the operating model over the next quarter. One entity. No systems programme. "
        "Not a police or fraud matter. Nobody else is in the room."
    )
    raw = {
        "work_signals": [{"value": "strategy", "evidence_span": "view on the operating model"}],
        "jurisdiction_names": '["United Kingdom"]',
        "entity_count": "1",
        "workstream_count": "1",
        "deadline_kind": "soft",
        "regulator_or_investigation": "false",
        "systems_change": "false",
        "multi_party": "false",
        "intake_kind": "enquiry",
        "stated_company": "Harbor & Pine",
        "stated_industry": "consumer",
        "stated_company_size": "sme",
        "stated_urgency": "low",
    }
    extraction = Extraction.model_validate(coerce_extraction_payload(raw, source))
    checked, rejected = validate_evidence_spans(extraction, source)
    assert checked.work_signals[0].value == WorkSignal.STRATEGY
    assert checked.stated_company.value == "Harbor & Pine"
    assert checked.jurisdiction_names.value == ["UK"]
    assert checked.entity_count.value == 1
    assert checked.systems_change.value is False
    assert "jurisdiction_names" not in rejected
    assert checked.stated_company_size.value == "sme"


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
