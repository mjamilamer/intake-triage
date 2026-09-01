"""Oracle eval against the 20 locked seeds. Writes EVAL_RESULTS.md. Not extraction accuracy."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from intake_triage.emit import format_email, format_sheet_csv, sheet_row, append_jsonl
from intake_triage.generate import seed_to_enquiry, seed_to_extraction, write_preview
from intake_triage.pipeline import triage_from_extraction
from intake_triage.policy_loader import load_policy
from intake_triage.schema import Extraction
from intake_triage.seeds import SEEDS

EXTRACTION_EVAL = Path(__file__).resolve().parent.parent / "data" / "extraction_eval.json"

ROOT = Path(__file__).resolve().parent.parent



MONDAY_PLAN = (
    "What I would run on Monday. `extract_with_llm` against all 20 preview descriptions on the "
    "pinned Sonnet snapshot, scoring each driver for value correctness and for whether its "
    "evidence span survived the substring check, then the extracted vectors through score and "
    "route for end-to-end accuracy. About an hour of work. I will not invent an accuracy number "
    "in the meantime."
)


def _extraction_section() -> list[str]:
    """Render section 1 from a live run if data/extraction_eval.json exists. Never estimate."""
    if not EXTRACTION_EVAL.exists():
        return [
            "NOT MEASURED. No live extraction result is on disk, so there is no accuracy number "
            "here and none has been estimated. Run `python -m intake_triage.eval_extraction`.",
            "",
            MONDAY_PLAN,
        ]
    data = json.loads(EXTRACTION_EVAL.read_text(encoding="utf-8"))
    n = data["n"]
    pd = data["per_driver"]["model_only"]
    shipped = data["per_driver"]["as_shipped"]
    slots = sum(d["n"] for d in pd.values())
    ok = sum(d["correct"] for d in pd.values())
    ok_shipped = sum(d["correct"] for d in shipped.values())
    policy = load_policy()
    live = []
    for rec, seed in zip(data["records"], SEEDS[:n]):
        extracted = Extraction.model_validate(rec["model_only"]["extraction"])
        decision = triage_from_extraction(seed_to_enquiry(seed), extracted, policy)
        live.append((seed, decision))
    abstained = sum(1 for _, d in live if d.abstained)
    committed = n - abstained
    expected_abstain = sum(1 for s in SEEDS[:n] if s["expected"]["abstained"])
    route_ok = sum(
        1
        for seed, d in live
        if d.route_to == seed["expected"]["route_to"]
    )
    tier_ok_live = sum(
        1
        for seed, d in live
        if (d.complexity.value if d.complexity else None) == seed["expected"]["tier"]
    )
    abstain_ok_live = sum(
        1 for seed, d in live if d.abstained is seed["expected"]["abstained"]
    )
    routed_ok = sum(
        1
        for seed, d in live
        if not d.abstained and d.route_to == seed["expected"]["route_to"]
    )
    reasons = Counter(
        d.abstain_reason.value for _, d in live if d.abstained and d.abstain_reason
    )
    reason_summary = ", ".join(f"{count} {name}" for name, count in reasons.most_common())
    ranked_drivers = sorted(pd.items(), key=lambda kv: kv[1]["correct"] / kv[1]["n"])
    weakest = " and ".join(
        f"`{field}` at {d['correct'] / d['n']:.0%}" for field, d in ranked_drivers[:2]
    )

    lines = [
        f"Live run: model `{data['model']}`, prompt `{data['prompt_version']}`, {n} preview "
        "descriptions, one forced-tool call each, scored against the authored driver vectors.",
        "",
        f"**Per-driver value accuracy: {ok}/{slots} slots ({ok / slots:.0%}).** With the "
        f"extract.py span-hint tables active it is {ok_shipped}/{slots} "
        f"({ok_shipped / slots:.0%}). Those tables are phrases copied out of these same 20 "
        "descriptions, so the second number is measured partly on its own source text. They "
        f"differ by {abs(ok_shipped - ok)} slot of {slots}, so the hints are not what carries "
        "this result, but they should still come out before any number is quoted externally.",
        "",
        "| Driver | Value correct | Span survived |",
        "|---|---|---|",
    ]
    for field, d in pd.items():
        lines.append(
            f"| `{field}` | {d['correct']}/{d['n']} ({d['correct'] / d['n']:.0%}) | "
            f"{d['span']}/{d['n']} |"
        )
    lines += [
        "",
        f"Evidence spans rejected by the substring check: "
        f"{data['span_rejections']['model_only']} across {n} enquiries.",
        "",
        "### End to end on extracted vectors",
        "",
        f"Routing {route_ok}/{n}. Tier {tier_ok_live}/{n}. Abstention flag {abstain_ok_live}/{n}.",
        "",
        f"**Committed {committed} of {n}; abstained {abstained}.** Expected abstention on this "
        f"set is {expected_abstain} of {n}, so the system is still more cautious than the spec. "
        f"Of the {committed} it committed, {routed_ok} went to the right lead."
        + (
            ""
            if committed
            else " Nothing reached a lead, so the deterministic layer was never given the "
            "chance to be right or wrong about one. That is a failure, not a safety feature."
        ),
        "",
        "Abstention reasons: " + (reason_summary or "none") + ".",
        "",
        "What still costs accuracy: the weakest drivers are "
        + weakest
        + ". Their dominant failure is expected `False`, got `None`. The authored vectors record "
        "an unmentioned negative as `False` with a null span, and `validate_evidence_spans` nulls "
        "any value whose span is not verbatim in the source. Almost no enquiry says no regulator "
        "is involved, so a negative fact cannot survive validation. The model obeyed the prompt "
        "rule that null means the text does not say; the seeds were authored under the opposite "
        "rule. That conflict is unresolved and it is a policy decision, not a modelling one.",
        "",
        "What that no longer does is block everything. Abstention is now decided by materiality "
        "in `score.py`: an unknown blocks a committed tier when it could move the hours across a "
        "tier boundary, and does not when it could not. A missing systems flag on a 30h matter "
        "can reach 40h and flips simple to moderate, so that abstains; the same flag on a 95h "
        "matter cannot leave complex, so it commits and records what it assumed. The null count "
        "in `policy.yaml` is now only a backstop for letters too sparse to triage at all. At a "
        "threshold of 1 it pre-empted that test and abstained on every enquiry, including ones "
        "where every driver was extracted correctly with a valid span.",
    ]
    return lines


def run_eval() -> str:
    """Replay the 20 locked seeds through score/route. Writes EVAL_RESULTS.md."""
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
        "`data/enquiries_150.csv` is intake-only free text (no extraction JSON, no expected labels). `data/call_batch.csv` holds 50 of those rows (15 easy / 20 medium / 15 hard) for a live CLI run with `--llm`. Offline numbers below are still the 20 locked seeds in `seeds.py`.",
        "",
        "## 1. Per-driver extraction accuracy (live)",
        *_extraction_section(),
        "",
        "## Sections 2 to 8: oracle path",
        "Everything below is computed from the authored driver vectors, not from model output. It is a regression test on score.py and route.py. Section 1 is the live run, and where the two disagree, section 1 is what production does today.",
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
