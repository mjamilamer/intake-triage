"""Walk a form dump row by row. One failure is one HOLD row, not a stalled morning."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from intake_triage.emit import format_email, sheet_row
from intake_triage.generate import seed_to_enquiry, seed_to_extraction
from intake_triage.pipeline import triage_from_extraction
from intake_triage.failsafe import handle_failure
from intake_triage.policy_loader import load_policy
from intake_triage.schema import Enquiry, Extraction
from intake_triage.seeds import SEEDS


def load_csv(path: Path) -> list[dict]:
    """Read an intake CSV. Columns are form fields plus split/difficulty metadata."""
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def lookup_record(enquiry_id: str, rows: list[dict] | None = None) -> dict:
    """Resolve an id from a CSV first, then from the 20 locked seeds."""
    if rows:
        for row in rows:
            if row["enquiry_id"] == enquiry_id:
                return row
    seed = next((s for s in SEEDS if s["enquiry_id"] == enquiry_id), None)
    if seed:
        return {
            "enquiry_id": seed["enquiry_id"],
            "submitted_at": seed["submitted_at"],
            "contact_name": seed.get("contact_name") or "",
            "contact_email": seed.get("contact_email") or "",
            "company_name": seed["company_name"],
            "industry": seed["industry"],
            "company_size": seed["company_size"],
            "urgency": seed["urgency"],
            "description": seed["description"],
            "difficulty": "",
            "split": "locked",
            "hard_case_type": seed.get("hard_case_type") or "",
        }
    raise KeyError(f"No enquiry {enquiry_id}")


def authored_extraction(enquiry_id: str) -> Extraction | None:
    """Gold drivers for HG-2026-0001..0020. Generated ids have none."""
    seed = next((s for s in SEEDS if s["enquiry_id"] == enquiry_id), None)
    if not seed:
        return None
    return seed_to_extraction(seed)


def row_to_enquiry(row: dict) -> Enquiry:
    """Map a CSV row onto the Enquiry schema. Blank picklists become null."""
    return seed_to_enquiry(
        {
            "enquiry_id": row["enquiry_id"],
            "submitted_at": row["submitted_at"],
            "contact_name": row.get("contact_name") or None,
            "contact_email": row.get("contact_email") or None,
            "company_name": row["company_name"],
            "industry": row["industry"],
            "company_size": row["company_size"],
            "urgency": row["urgency"],
            "description": row.get("description") or "",
        }
    )


def row_extraction(row: dict, *, use_llm: bool) -> tuple[Extraction, str, str | None]:
    """CSVs are intake-only. Offline facts come from the 20 locked seeds, never from the file."""
    if use_llm:
        key = __import__("os").environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set. pip install -e \".[llm]\" and export the key.")
        from intake_triage.extract import extract_with_llm

        return extract_with_llm(row.get("description") or "", api_key=key), "live_llm", None
    authored = authored_extraction(row.get("enquiry_id") or "")
    if authored is not None:
        return authored, "authored_drivers", None
    return (
        Extraction(),
        "empty",
        "Intake-only row. Pass --llm to extract, or use a locked seed HG-2026-0001..0020.",
    )


def _pack(enquiry: Enquiry, extraction: Extraction, decision, *, source: str, row: dict, error: str | None) -> dict:
    return {
        "enquiry_id": enquiry.enquiry_id,
        "difficulty": row.get("difficulty") or "",
        "split": row.get("split") or "",
        "extraction_source": source,
        "error": error,
        "decision": {
            "abstained": decision.abstained,
            "abstain_reason": decision.abstain_reason.value if decision.abstain_reason else None,
            "service_line": decision.service_line.value if decision.service_line else None,
            "complexity": decision.complexity.value if decision.complexity else None,
            "estimated_hours": decision.estimated_hours,
            "route_to": decision.route_to,
        },
        "rule_trace": decision.rule_trace,
        "extraction": extraction.model_dump(mode="json"),
        "intake": {
            "company_name": enquiry.company_name,
            "industry": enquiry.industry.value if enquiry.industry else None,
            "company_size": enquiry.company_size.value if enquiry.company_size else None,
            "urgency": enquiry.urgency.value if enquiry.urgency else None,
            "description": enquiry.description,
        },
        "email": format_email(enquiry, decision, load_policy()),
        "sheet_row": sheet_row(enquiry, decision),
        "output_json": decision.model_dump(mode="json"),
    }


def process_row(row: dict, *, use_llm: bool = False) -> dict:
    """Score one CSV row. Failures become abstentions; they do not raise."""
    policy = load_policy()
    try:
        enquiry = row_to_enquiry(row)
    except Exception as exc:  # noqa: BLE001
        # Unparseable row. The letter still reaches the analyst with an email and a
        # JSON copy; an enquiry is never dropped because a field would not coerce.
        subject, decision, _ = handle_failure(row, exc, policy=policy, stage="intake parse")
        return _pack(subject, Extraction(), decision, source="failed", row=row, error=str(exc))
    try:
        extraction, source, warn = row_extraction(row, use_llm=use_llm)
        decision = triage_from_extraction(enquiry, extraction, policy)
        return _pack(enquiry, extraction, decision, source=source, row=row, error=warn)
    except Exception as exc:  # noqa: BLE001
        # Model outage, bad tool call, schema rejection. Abstain as extraction_failed
        # rather than low_evidence: an outage and a terse letter must not look alike.
        _, decision, _ = handle_failure(
            row, exc, enquiry=enquiry, policy=policy, stage="extraction"
        )
        return _pack(enquiry, Extraction(), decision, source="failed", row=row, error=str(exc))


def process_batch(
    rows: list[dict],
    *,
    use_llm: bool = False,
    difficulty: str | None = None,
    limit: int | None = None,
    out_dir: Path | None = None,
) -> dict:
    """Each row is independent. One failure does not stop the batch.

    This is a morning spreadsheet dump, not a queue. Sequential extract is
    enough at 40-60/week. Parallel workers become a discussion around 500/week.
    """
    if difficulty:
        rows = [r for r in rows if r.get("difficulty") == difficulty]
    if limit is not None:
        rows = rows[:limit]
    batch_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    results = [process_row(row, use_llm=use_llm) for row in rows]
    summary = {
        "batch_id": batch_id,
        "n": len(results),
        "abstained": sum(1 for r in results if r["decision"]["abstained"]),
        "errors": sum(1 for r in results if r["error"]),
        "extraction": "live_llm" if use_llm else "authored_seeds_or_empty",
        "by_tier": {},
        "by_difficulty": {},
        "by_extraction_source": {},
    }
    for item in results:
        tier = item["decision"]["complexity"] or "abstain"
        summary["by_tier"][tier] = summary["by_tier"].get(tier, 0) + 1
        diff = item["difficulty"] or "unspecified"
        summary["by_difficulty"][diff] = summary["by_difficulty"].get(diff, 0) + 1
        src = item["extraction_source"]
        summary["by_extraction_source"][src] = summary["by_extraction_source"].get(src, 0) + 1
    if not use_llm:
        summary["note"] = (
            "CSV files are form dumps. Offline scoring uses the 20 locked seeds in seeds.py. "
            "Generated ids need --llm."
        )

    if out_dir:
        dest = out_dir / batch_id
        dest.mkdir(parents=True, exist_ok=True)
        jsonl = dest / "decisions.jsonl"
        csv_path = dest / "decisions.csv"
        with jsonl.open("w", encoding="utf-8") as handle:
            for item in results:
                handle.write(json.dumps(item["output_json"]) + "\n")
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "enquiry_id",
                    "difficulty",
                    "abstained",
                    "abstain_reason",
                    "service_line",
                    "complexity",
                    "estimated_hours",
                    "route_to",
                    "error",
                ],
            )
            writer.writeheader()
            for item in results:
                d = item["decision"]
                writer.writerow(
                    {
                        "enquiry_id": item["enquiry_id"],
                        "difficulty": item["difficulty"],
                        "abstained": d["abstained"],
                        "abstain_reason": d["abstain_reason"] or "",
                        "service_line": d["service_line"] or "",
                        "complexity": d["complexity"] or "",
                        "estimated_hours": d["estimated_hours"] if d["estimated_hours"] is not None else "",
                        "route_to": d["route_to"] or "",
                        "error": item["error"] or "",
                    }
                )
        summary["out_dir"] = str(dest)
    return {"summary": summary, "results": results}


def format_single(result: dict) -> str:
    """Human-readable one-enquiry printout for the terminal."""
    d = result["decision"]
    lines = [
        f"ID {result['enquiry_id']}",
        f"INTAKE  {result['intake']['company_name']}  {result['intake']['industry']}  {result['intake']['company_size']}",
        "",
        result["intake"]["description"],
        "",
        f"EXTRACT ({result['extraction_source']})",
        json.dumps(result["extraction"], indent=2),
        "",
        "TRACE",
        *result["rule_trace"],
        "",
        f"OUTPUT  abstained={d['abstained']}  {d['abstain_reason'] or d['service_line']}  {d['complexity']}  {d['estimated_hours']}h",
        f"ROUTE   {d['route_to']}",
    ]
    if result["error"]:
        lines.append(f"NOTE    {result['error']}")
    return "\n".join(lines)
