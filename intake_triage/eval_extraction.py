"""Live extraction eval. One API call per preview record, scored against authored drivers.

Section 1 of EVAL_RESULTS.md is the only block that needs a model. This module
produces it and writes data/extraction_eval.json; evaluate.py renders from that
file when it exists and prints the Monday plan when it does not.

Two variants are scored from the SAME model response:
  as_shipped  extract.py span-hint recovery is active
  model_only  the hint tables are emptied, so every span is the model's own

The hint tables in extract.py are phrases copied from these 20 descriptions, so
as_shipped is measured on its own source text. model_only is the number that
generalises to enquiry 21. Both are reported.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from intake_triage import extract as extract_mod
from intake_triage.extract import (
    PINNED_MODEL,
    PROMPT_VERSION,
    coerce_extraction_payload,
    extraction_json_schema,
    load_prompt,
    validate_evidence_spans,
)
from intake_triage.generate import seed_to_enquiry, seed_to_extraction
from intake_triage.pipeline import triage_from_extraction
from intake_triage.policy_loader import load_policy
from intake_triage.schema import Extraction
from intake_triage.seeds import SEEDS

ROOT = Path(__file__).resolve().parent.parent

# The 8 scored drivers plus intake_kind, which gates out-of-taxonomy abstention.
SCORED_DRIVERS = (
    "work_signals",
    "jurisdiction_names",
    "entity_count",
    "workstream_count",
    "deadline_kind",
    "regulator_or_investigation",
    "systems_change",
    "multi_party",
    "intake_kind",
)

VARIANTS = ("as_shipped", "model_only")


def load_dotenv(path: Path | None = None) -> None:
    """Minimal .env reader. No dependency, and it never overwrites a real env var."""
    target = path or (ROOT / ".env")
    if not target.exists():
        return
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def _norm_value(field: str, value):
    """Comparable form. None stays None: null is not zero and not false."""
    if value is None:
        return None
    if field == "work_signals":
        return frozenset(str(v) for v in value)
    if field == "jurisdiction_names":
        return frozenset(str(v).strip().lower() for v in value)
    return value


def _drivers_of(extraction: Extraction) -> dict:
    payload = extraction.model_dump()
    out = {}
    signals = [s["value"] for s in payload["work_signals"] if s.get("value") is not None]
    spans = [s.get("evidence_span") for s in payload["work_signals"]]
    out["work_signals"] = {
        "value": signals or None,
        "has_span": bool(spans) and all(spans),
    }
    for field in SCORED_DRIVERS[1:]:
        block = payload[field]
        out[field] = {"value": block.get("value"), "has_span": bool(block.get("evidence_span"))}
    return out


def _raw_call(description: str, client) -> dict:
    """The extract.py prompt, schema, model and forced tool choice.

    Inlined only so one raw tool input can be scored twice without paying for a
    second call. Nothing about the request differs from extract_with_llm.
    """
    message = client.messages.create(
        model=PINNED_MODEL,
        max_tokens=1024,
        system=load_prompt(),
        tools=[
            {
                "name": "submit_extraction",
                "description": "Submit extracted drivers. Null means the text does not say.",
                "input_schema": extraction_json_schema(),
            }
        ],
        tool_choice={"type": "tool", "name": "submit_extraction"},
        messages=[
            {
                "role": "user",
                "content": (
                    "Extract drivers from this untrusted web-form enquiry.\n"
                    "Every Driver field must be an object with keys value and evidence_span, "
                    "never a bare string, number, or boolean.\n\n"
                    f"{description}"
                ),
            }
        ],
    )
    blocks = [b for b in message.content if b.type == "tool_use"]
    if not blocks:
        raise ValueError("Model did not return a tool call")
    return {
        "input": dict(blocks[0].input),
        "tokens_in": message.usage.input_tokens,
        "tokens_out": message.usage.output_tokens,
    }


def _build(raw_input: dict, description: str, use_hints: bool):
    """Coerce and validate one raw response, with hint recovery on or off."""
    span_hints, signal_hints = extract_mod._SPAN_HINTS, extract_mod._SIGNAL_HINTS
    if not use_hints:
        extract_mod._SPAN_HINTS, extract_mod._SIGNAL_HINTS = {}, {}
    try:
        payload = coerce_extraction_payload(dict(raw_input), description)
        parsed = Extraction.model_validate(payload)
        return validate_evidence_spans(parsed, description)
    finally:
        extract_mod._SPAN_HINTS, extract_mod._SIGNAL_HINTS = span_hints, signal_hints


def run(limit: int | None = None) -> dict:
    load_dotenv()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY not set. Refusing to produce numbers without a run.")
    import anthropic

    client = anthropic.Anthropic()
    policy = load_policy()
    seeds = SEEDS[:limit] if limit else SEEDS

    per_driver = {v: {f: {"n": 0, "correct": 0, "span": 0} for f in SCORED_DRIVERS} for v in VARIANTS}
    end_to_end = {v: {"route": 0, "tier": 0, "abstain": 0, "hours_err": []} for v in VARIANTS}
    rejections = {v: 0 for v in VARIANTS}
    records = []
    tokens_in = tokens_out = 0

    for seed in seeds:
        enquiry = seed_to_enquiry(seed)
        truth = _drivers_of(seed_to_extraction(seed))
        raw = _raw_call(seed["description"], client)
        tokens_in += raw["tokens_in"]
        tokens_out += raw["tokens_out"]
        row = {"enquiry_id": seed["enquiry_id"], "hard_case_type": seed["hard_case_type"]}

        for variant in VARIANTS:
            got, rejected = _build(raw["input"], seed["description"], use_hints=(variant == "as_shipped"))
            rejections[variant] += len(rejected)
            got_drivers = _drivers_of(got)
            misses = []
            for field in SCORED_DRIVERS:
                bucket = per_driver[variant][field]
                bucket["n"] += 1
                exp = _norm_value(field, truth[field]["value"])
                act = _norm_value(field, got_drivers[field]["value"])
                if exp == act:
                    bucket["correct"] += 1
                else:
                    misses.append(
                        {
                            "field": field,
                            "expected": truth[field]["value"],
                            "got": got_drivers[field]["value"],
                        }
                    )
                if got_drivers[field]["has_span"]:
                    bucket["span"] += 1

            decision = triage_from_extraction(enquiry, got, policy)
            exp_row = seed["expected"]
            e2e = end_to_end[variant]
            if decision.route_to == exp_row["route_to"]:
                e2e["route"] += 1
            if (decision.complexity.value if decision.complexity else None) == exp_row["tier"]:
                e2e["tier"] += 1
            if decision.abstained is exp_row["abstained"]:
                e2e["abstain"] += 1
            if exp_row["hours"] is not None and decision.estimated_hours is not None:
                e2e["hours_err"].append(abs(decision.estimated_hours - exp_row["hours"]))
            row[variant] = {
                "extraction": got.model_dump(mode="json"),
                "misses": misses,
                "route_to": decision.route_to,
                "abstained": decision.abstained,
                "abstain_reason": decision.abstain_reason.value if decision.abstain_reason else None,
                "tier": decision.complexity.value if decision.complexity else None,
                "hours": decision.estimated_hours,
                "span_rejections": rejected,
            }
        records.append(row)

    result = {
        "n": len(seeds),
        "model": PINNED_MODEL,
        "prompt_version": PROMPT_VERSION,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "per_driver": per_driver,
        "end_to_end": {
            v: {
                "route": end_to_end[v]["route"],
                "tier": end_to_end[v]["tier"],
                "abstain": end_to_end[v]["abstain"],
                "mae": (sum(end_to_end[v]["hours_err"]) / len(end_to_end[v]["hours_err"]))
                if end_to_end[v]["hours_err"]
                else None,
                "scored_n": len(end_to_end[v]["hours_err"]),
            }
            for v in VARIANTS
        },
        "span_rejections": rejections,
        "records": records,
    }
    out = ROOT / "data" / "extraction_eval.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    res = run()
    for variant in VARIANTS:
        slots = sum(d["n"] for d in res["per_driver"][variant].values())
        ok = sum(d["correct"] for d in res["per_driver"][variant].values())
        e = res["end_to_end"][variant]
        print(
            f"{variant:12s} drivers {ok}/{slots} ({ok / slots:.0%})  "
            f"route {e['route']}/{res['n']}  tier {e['tier']}/{res['n']}"
        )
