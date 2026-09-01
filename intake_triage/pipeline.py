from __future__ import annotations

from intake_triage.policy_loader import load_policy
from intake_triage.route import decide
from intake_triage.schema import Enquiry, Extraction, TriageDecision


def triage_from_extraction(
    enquiry: Enquiry,
    extraction: Extraction,
    policy: dict | None = None,
) -> TriageDecision:
    """Deterministic path used by tests, the notebook, and shadow mode."""
    policy = policy or load_policy()
    return decide(enquiry, extraction, policy)
