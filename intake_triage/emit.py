from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path

from intake_triage.schema import Enquiry, TriageDecision


def format_email(enquiry: Enquiry, decision: TriageDecision, policy: dict) -> str:
    if decision.abstained:
        to_name = "Intake analyst"
        to_addr = policy["analyst_email"]
        heading = "ABSTAINED: needs a human decision"
        candidates = []
        for item in decision.competing_lines:
            lead = policy["leads"].get(item.owner, {}).get("name", item.owner)
            candidates.append(
                f"- {item.service_line.value}: {item.hours}h to {lead} ({item.owner})"
            )
        candidate_block = "\n".join(candidates) if candidates else "- none scored"
        decision_block = (
            f"{heading}\nReason: {decision.abstain_reason.value if decision.abstain_reason else 'unspecified'}\n"
            f"Reply 1 or 2, or name the correct line.\n\nCandidates:\n{candidate_block}"
        )
    else:
        lead = policy["leads"].get(decision.route_to, {}).get("name", decision.route_to)
        to_name = lead
        to_addr = decision.route_to
        decision_block = (
            f"Service line: {decision.service_line.value}\n"
            f"Complexity: {decision.complexity.value}\n"
            f"Estimated hours: {decision.estimated_hours}\n"
            f"Route to: {to_name} ({to_addr})"
        )

    trace = "\n".join(f"- {line}" for line in decision.rule_trace)
    return (
        f"To: {to_addr}\n"
        f"Subject: Intake {enquiry.enquiry_id} / {enquiry.company_name}\n\n"
        f"{decision_block}\n\n"
        f"Rule trace:\n{trace}\n\n"
        f"Original enquiry\n"
        f"Company: {enquiry.company_name}\n"
        f"Industry: {enquiry.industry.value}\n"
        f"Size: {enquiry.company_size.value}\n"
        f"Urgency (form field, not complexity): {enquiry.urgency.value}\n\n"
        f"{enquiry.description}\n"
    )


SHEET_COLUMNS = [
    "enquiry_id",
    "submitted_at",
    "company_name",
    "industry",
    "company_size",
    "urgency",
    "service_line",
    "complexity",
    "estimated_hours",
    "route_to",
    "abstained",
    "abstain_reason",
    "correction",
    "model_version",
    "prompt_version",
]


def sheet_row(enquiry: Enquiry, decision: TriageDecision) -> dict:
    return {
        "enquiry_id": enquiry.enquiry_id,
        "submitted_at": enquiry.submitted_at.isoformat(),
        "company_name": enquiry.company_name,
        "industry": enquiry.industry.value,
        "company_size": enquiry.company_size.value,
        "urgency": enquiry.urgency.value,
        "service_line": decision.service_line.value if decision.service_line else "",
        "complexity": decision.complexity.value if decision.complexity else "",
        "estimated_hours": decision.estimated_hours if decision.estimated_hours is not None else "",
        "route_to": decision.route_to or "",
        "abstained": decision.abstained,
        "abstain_reason": decision.abstain_reason.value if decision.abstain_reason else "",
        "correction": "",
        "model_version": decision.model_version or "",
        "prompt_version": decision.prompt_version or "",
    }


def format_sheet_csv(rows: list[dict]) -> str:
    buf = StringIO()
    writer = csv.DictWriter(buf, fieldnames=SHEET_COLUMNS)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def append_jsonl(path: Path, decision: TriageDecision) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(decision.model_dump_json() + "\n")
