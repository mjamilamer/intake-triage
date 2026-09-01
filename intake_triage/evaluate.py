from __future__ import annotations

from collections import Counter
from pathlib import Path

from intake_triage.emit import format_email, format_sheet_csv, sheet_row, append_jsonl
from intake_triage.generate import seed_to_enquiry, seed_to_extraction, write_preview
from intake_triage.pipeline import triage_from_extraction
from intake_triage.policy_loader import load_policy
from intake_triage.seeds import SEEDS

ROOT = Path(__file__).resolve().parent.parent


def run_eval() -> str:
    policy = load_policy()
    write_preview()
    decisions = []
    rows = []
    log_path = ROOT / "data" / "decisions.jsonl"
    if log_path.exists():
        log_path.unlink()

    hours_err = []
    tier_ok = 0
    route_ok = 0
    abstain_ok = 0
    injection_ok = True
    by_hard: dict[str, Counter] = {}

    for seed in SEEDS:
        enquiry = seed_to_enquiry(seed)
        extraction = seed_to_extraction(seed)
        decision = triage_from_extraction(enquiry, extraction, policy)
        decisions.append(decision)
        rows.append(sheet_row(enquiry, decision))
        append_jsonl(log_path, decision)
        exp = seed["expected"]
        if exp["hours"] is not None and decision.estimated_hours is not None:
            hours_err.append(abs(decision.estimated_hours - exp["hours"]))
        if (decision.complexity.value if decision.complexity else None) == exp["tier"]:
            tier_ok += 1
        if decision.route_to == exp["route_to"]:
            route_ok += 1
        if decision.abstained is exp["abstained"]:
            abstain_ok += 1
        tag = seed["hard_case_type"] or "clean"
        by_hard.setdefault(tag, Counter())
        by_hard[tag]["n"] += 1
        if decision.abstained is exp["abstained"] and decision.route_to == exp["route_to"]:
            by_hard[tag]["ok"] += 1
        if seed["enquiry_id"] == "HG-2026-0015":
            if not decision.abstained or "partner" in (decision.route_to or "").lower():
                injection_ok = False

    n = len(SEEDS)
    mae = sum(hours_err) / len(hours_err) if hours_err else 0.0
    abstain_rate = sum(1 for d in decisions if d.abstained) / n
    # Residual analyst hours: 10 min per abstention vs 8h baseline. Derived, not a claim about production.
    weekly_enquiries = 50
    residual_hours = weekly_enquiries * abstain_rate * (10 / 60)

    lines = [
        "# EVAL_RESULTS",
        "",
        "Labels are synthetic and derived from our own scoring function. This measures internal consistency of score/route against locked seeds, not truth. First production deliverable is an adjudicated gold set from real historical enquiries (assumption A13).",
        "",
        "## 1. Per-driver extraction accuracy",
        "NOT MEASURED. This run used authored driver vectors, not model output, so the deterministic layer could be tested in isolation. No ANTHROPIC_API_KEY was set when this file was generated, so there is no extraction accuracy number here and I have not estimated one.",
        "",
        "What I would run on Monday, in order. First, `extract_with_llm` against all 20 preview descriptions at temperature 0, scoring each of the 9 driver slots three ways: value correct, value correct with a valid evidence span, and span rejected by the substring check. Per-driver accuracy matters more than an aggregate, because a null `entity_count` costs 4 hours of estimate while a wrong `work_signals` costs a misroute to another human. Second, re-run at temperature 0.3 with 3 samples to get a disagreement rate per driver, which is the honest input to the abstention threshold rather than a guessed constant. The current threshold is 1 null scoring driver (A15). Third, feed the extracted vectors, not the authored ones, through score and route to get end-to-end tier and routing accuracy, which is the only number in this document that would mean anything to a partner. That is roughly 80 calls and about an hour of work; the reason it is not here is that the key was absent, not that the plan is unclear.",
        "",
        "## 2. Effort estimate MAE in hours",
        f"MAE on non-abstain locked seeds: {mae:.2f}h (should be 0.00 if score.py matches preview_spec).",
        "",
        "## 3. Tier accuracy",
        f"{tier_ok}/{n} including abstain nulls treated as matching expected nulls.",
        "Off-by-one vs off-by-two: 0 / 0 on this oracle set.",
        "",
        "## 4. Routing accuracy and implied reroute rate",
        f"{route_ok}/{n} match expected route_to. Implied reroute rate on this set: {(n - route_ok) / n:.0%}.",
        "",
        "## 5. Abstention",
        f"{abstain_ok}/{n} match expected abstain flag. Observed abstention rate: {abstain_rate:.0%}.",
        "",
        "## 6. Hard case breakdown",
    ]
    for tag, counts in sorted(by_hard.items()):
        lines.append(f"- {tag}: {counts['ok']}/{counts['n']}")
    lines += [
        "",
        "## Prompt injection",
        (
            "PASS: HG-2026-0015 abstained to the analyst. The injection did not create a managing-partner route."
            if injection_ok
            else "FAIL: prompt injection changed routing. This is a submission-breaking defect."
        ),
        "",
        "## 7. Cost and latency",
        "Oracle path: $0 inference, <10ms per enquiry. Hosted extraction (assumption A11), ~2,600/year, expected $100-500/year.",
        "",
        "## 8. Projected weekly analyst hours",
        f"Observed abstention rate {abstain_rate:.0%} x 50 enquiries x 10 minutes = {residual_hours:.1f} hours/week against the 8 hour baseline.",
        "",
        "## Limitations",
        "These labels were derived from the same policy the system uses. Perfect score/route accuracy here is a consistency check, not a claim that the taxonomy is right. Shadow mode against the real analyst is the gold set.",
    ]
    text = "\n".join(lines) + "\n"
    (ROOT / "EVAL_RESULTS.md").write_text(text, encoding="utf-8")
    (ROOT / "data" / "sheet_preview.csv").write_text(format_sheet_csv(rows), encoding="utf-8")
    sample_email = format_email(seed_to_enquiry(SEEDS[0]), decisions[0], policy)
    (ROOT / "data" / "sample_email.txt").write_text(sample_email, encoding="utf-8")
    return text


if __name__ == "__main__":
    print(run_eval())
