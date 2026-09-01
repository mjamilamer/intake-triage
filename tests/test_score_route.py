"""Locked seeds through score/route. Cross-lead holds; same-lead overlap routes."""

from __future__ import annotations

from intake_triage.generate import seed_to_enquiry, seed_to_extraction
from intake_triage.pipeline import triage_from_extraction
from intake_triage.schema import ComplexityTier, Extraction, ServiceLine
from intake_triage.score import score, tier_for
from intake_triage.seeds import SEEDS
from intake_triage.policy_loader import load_policy


def test_all_locked_seeds():
    policy = load_policy()
    for seed in SEEDS:
        enquiry = seed_to_enquiry(seed)
        extraction = seed_to_extraction(seed)
        decision = triage_from_extraction(enquiry, extraction, policy)
        exp = seed["expected"]
        assert decision.abstained is exp["abstained"], seed["enquiry_id"]
        if exp["abstain_reason"]:
            assert decision.abstain_reason.value == exp["abstain_reason"], seed["enquiry_id"]
        else:
            assert decision.abstain_reason is None, seed["enquiry_id"]
        assert decision.route_to == exp["route_to"], seed["enquiry_id"]
        if not exp["abstained"]:
            assert decision.estimated_hours == exp["hours"], seed["enquiry_id"]
            assert decision.complexity.value == exp["tier"], seed["enquiry_id"]
            assert decision.service_line.value == exp["service_line"], seed["enquiry_id"]
        else:
            assert decision.service_line is None, seed["enquiry_id"]
            # Injection must never create a managing-partner route.
            assert decision.route_to == policy["analyst_email"]


def test_tier_boundaries_inclusive():
    policy = load_policy()
    # 40 is inclusive on moderate. 80 is inclusive on complex.
    assert tier_for(39, policy) == ComplexityTier.SIMPLE
    assert tier_for(40, policy) == ComplexityTier.MODERATE
    assert tier_for(79, policy) == ComplexityTier.MODERATE
    assert tier_for(80, policy) == ComplexityTier.COMPLEX


def test_all_null_does_not_score_tax_base():
    enquiry = seed_to_enquiry(next(s for s in SEEDS if s["enquiry_id"] == "HG-2026-0013"))
    extraction = Extraction()
    scored = score(extraction, enquiry)
    assert scored.low_evidence is True
    assert scored.estimated_hours is None
    decision = triage_from_extraction(enquiry, extraction)
    assert decision.abstained is True


def test_injection_wins_over_tech_signal():
    seed = next(s for s in SEEDS if s["enquiry_id"] == "HG-2026-0015")
    decision = triage_from_extraction(seed_to_enquiry(seed), seed_to_extraction(seed))
    assert decision.abstained is True
    assert "managing partner" not in (decision.route_to or "").lower()


def test_same_lead_overlap_does_not_abstain():
    seed = next(s for s in SEEDS if s["enquiry_id"] == "HG-2026-0012")
    decision = triage_from_extraction(seed_to_enquiry(seed), seed_to_extraction(seed))
    assert decision.abstained is False
    assert decision.service_line == ServiceLine.MA_TRANSACTION


def test_cross_lead_does_abstain():
    seed = next(s for s in SEEDS if s["enquiry_id"] == "HG-2026-0011")
    decision = triage_from_extraction(seed_to_enquiry(seed), seed_to_extraction(seed))
    assert decision.abstained is True
    assert decision.abstain_reason.value == "cross_lead_conflict"
    assert len(decision.competing_lines) == 2


def test_cross_lead_wins_over_null_deadline():
    seed = next(s for s in SEEDS if s["enquiry_id"] == "HG-2026-0011")
    extraction = seed_to_extraction(seed).model_copy(deep=True)
    extraction.deadline_kind.value = None
    extraction.deadline_kind.evidence_span = None
    decision = triage_from_extraction(seed_to_enquiry(seed), extraction)
    assert decision.abstained is True
    assert decision.abstain_reason.value == "cross_lead_conflict"
