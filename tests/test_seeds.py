"""Preview roundtrip for the 20 locked seeds."""

from __future__ import annotations

from intake_triage.generate import seed_to_enquiry, seed_to_extraction
from intake_triage.pipeline import triage_from_extraction
from intake_triage.seeds import SEEDS


def test_preview_roundtrip_count():
    assert len(SEEDS) == 20
    assert SEEDS[0]["enquiry_id"] == "HG-2026-0001"
    enquiry = seed_to_enquiry(SEEDS[0])
    extraction = seed_to_extraction(SEEDS[0])
    assert enquiry.company_name == "Northbridge Payroll Ltd"
    assert extraction.work_signals[0].value.value == "tax"
