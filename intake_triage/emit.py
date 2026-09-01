"""Lead email, spreadsheet row, and JSONL line. Form picklists win; empty forms use the letter."""

from __future__ import annotations

import csv
import re
from io import StringIO
from pathlib import Path

from intake_triage.schema import AbstainReason, Enquiry, Extraction, TriageDecision


def _enum_or_str(value) -> str | None:
    if value is None or value == "":
        return None
    return value.value if hasattr(value, "value") else str(value)


def _stated(extraction: Extraction | None, field: str) -> str | None:
    if extraction is None:
        return None
    driver = getattr(extraction, field, None)
    if driver is None:
        return None
    return _enum_or_str(driver.value)


def letter_brief(description: str, *, limit: int = 280) -> str:
    text = (description or "").strip()
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", text)
    brief = " ".join(parts[:2]).strip()
    if len(brief) > limit:
        clipped = brief[: limit - 1].rsplit(" ", 1)
        brief = (clipped[0] if clipped else brief[:limit]) + "..."
    return brief


def resolve_intake_fields(enquiry: Enquiry, extraction: Extraction | None) -> dict[str, tuple[str | None, str]]:
    """Form picklist wins. If empty, use stated_* from the letter."""
    pairs = (
        ("company", enquiry.company_name, "stated_company"),
        ("industry", _enum_or_str(enquiry.industry), "stated_industry"),
        ("size", _enum_or_str(enquiry.company_size), "stated_company_size"),
        ("urgency", _enum_or_str(enquiry.urgency), "stated_urgency"),
    )
    out: dict[str, tuple[str | None, str]] = {}
    for key, form_val, stated_field in pairs:
        if form_val:
            out[key] = (form_val, "form")
        else:
            letter_val = _stated(extraction, stated_field)
            out[key] = (letter_val, "letter") if letter_val else (None, "missing")
    return out


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
        reason = decision.abstain_reason.value if decision.abstain_reason else "unspecified"
        if decision.abstain_reason is AbstainReason.EXTRACTION_FAILED:
            # Nothing was scored, so there is nothing to choose between. Asking the
            # analyst to reply 1 or 2 against an empty candidate list wastes the
            # minute the failsafe is meant to buy them.
            heading = "NOT TRIAGED: the system failed on this enquiry"
            decision_block = (
                f"{heading}\nReason: {reason}\n"
                "Triage this one by hand. No service line, tier, or hours were produced,\n"
                "and no candidates were scored. The cause is in the rule trace below.\n"
                "This is a system failure, not a difficult enquiry."
            )
        else:
            decision_block = (
                f"{heading}\nReason: {reason}\n"
                f"Reply 1 or 2, or name the correct line.\n\nCandidates:\n{candidate_block}"
            )
    else:
        lead = policy["leads"].get(decision.route_to, {}).get("name", decision.route_to)
        to_name = lead
        to_addr = decision.route_to
        hours_line = f"Estimated hours: {decision.estimated_hours}"
        if any("IMMATERIAL UNKNOWN" in line for line in decision.rule_trace):
            hours_line += (
                " (omits unknown modifiers; worst case stays this tier. See rule trace.)"
            )
        decision_block = (
            f"Service line: {decision.service_line.value}\n"
            f"Complexity: {decision.complexity.value}\n"
            f"{hours_line}\n"
            f"Route to: {to_name} ({to_addr})"
        )

    fields = resolve_intake_fields(enquiry, decision.extraction)
    company, company_src = fields["company"]
    industry, industry_src = fields["industry"]
    size, size_src = fields["size"]
    urgency, urgency_src = fields["urgency"]
    display_company = company or "(unnamed)"
    form_empty = all(src != "form" for _, src in fields.values())

    def labelled(title: str, value: str | None, source: str) -> str:
        if not value:
            return f"{title}: (not on form; see letter)"
        if source == "letter":
            return f"{title}: {value} (from letter)"
        return f"{title}: {value}"

    original = [
        labelled("Company", company, company_src),
        labelled("Industry", industry, industry_src),
        labelled("Size", size, size_src),
        labelled("Urgency (form field, not complexity)", urgency, urgency_src),
    ]
    if form_empty:
        brief = letter_brief(enquiry.description)
        if brief:
            original.append(f"Brief (from letter): {brief}")

    trace = "\n".join(f"- {line}" for line in decision.rule_trace)
    return (
        f"To: {to_addr}\n"
        f"Subject: Intake {enquiry.enquiry_id} / {display_company}\n\n"
        f"{decision_block}\n\n"
        f"Rule trace:\n{trace}\n\n"
        f"Original enquiry\n"
        + "\n".join(original)
        + f"\n\n{enquiry.description}\n"
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
    fields = resolve_intake_fields(enquiry, decision.extraction)
    return {
        "enquiry_id": enquiry.enquiry_id,
        "submitted_at": enquiry.submitted_at.isoformat(),
        "company_name": fields["company"][0] or "",
        "industry": fields["industry"][0] or "",
        "company_size": fields["size"][0] or "",
        "urgency": fields["urgency"][0] or "",
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
