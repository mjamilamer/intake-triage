"""Reverse generation: 150 rows, 15/20/15 call split, spans appear in the letter."""

from __future__ import annotations

import csv
from collections import Counter

from intake_triage.extract import validate_evidence_spans
from intake_triage.generate import seed_to_extraction
from intake_triage.synth import assign_split, generate_records, write_csvs


MUST_CALL = {
    "HG-2026-0001",
    "HG-2026-0002",
    "HG-2026-0003",
    "HG-2026-0011",
    "HG-2026-0012",
    "HG-2026-0015",
}


def test_generate_150_call_split():
    records = assign_split(generate_records(150))
    assert len(records) == 150
    ids = [r["enquiry_id"] for r in records]
    assert len(set(ids)) == 150
    call = [r for r in records if r["split"] == "call"]
    corpus = [r for r in records if r["split"] == "corpus"]
    assert len(call) == 50
    assert len(corpus) == 100
    counts = Counter(r["difficulty"] for r in call)
    assert counts["easy"] == 15
    assert counts["medium"] == 20
    assert counts["hard"] == 15
    call_ids = {r["enquiry_id"] for r in call}
    assert MUST_CALL <= call_ids


def test_generated_spans_are_in_the_prose():
    records = generate_records(150)
    generated = [r for r in records if int(r["enquiry_id"].split("-")[-1]) > 20]
    assert generated
    for rec in generated:
        _, rejected = validate_evidence_spans(seed_to_extraction(rec), rec["description"])
        assert rejected == [], f"{rec['enquiry_id']} rejected {rejected}"


def test_write_csvs(tmp_path):
    records = assign_split(generate_records(150))
    paths = write_csvs(records, tmp_path)
    assert paths["all"].exists()
    call_text = paths["call"].read_text(encoding="utf-8")
    assert call_text.count("\n") == 51  # header + 50
    assert "description" in paths["all"].read_text(encoding="utf-8").splitlines()[0]
    with paths["call"].open(encoding="utf-8", newline="") as handle:
        call_ids = [row["enquiry_id"] for row in csv.DictReader(handle)]
    assert call_ids[:6] == [
        "HG-2026-0001",
        "HG-2026-0002",
        "HG-2026-0003",
        "HG-2026-0011",
        "HG-2026-0012",
        "HG-2026-0015",
    ]
    with paths["all"].open(encoding="utf-8", newline="") as handle:
        header = csv.DictReader(handle).fieldnames or []
    assert "description" in header
    assert "extraction_json" not in header
    assert "expected_hours" not in header
    assert "expected_tier" not in header
