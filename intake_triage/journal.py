from __future__ import annotations

import os
from pathlib import Path

from intake_triage.emit import format_email, sheet_row
from intake_triage.generate import seed_to_enquiry, seed_to_extraction
from intake_triage.policy_loader import load_policy
from intake_triage.route import _injection_hit, decide
from intake_triage.schema import Enquiry, Extraction, IntakeKind
from intake_triage.score import score as score_extraction
from intake_triage.seeds import SEEDS

STATIC_DIR = Path(__file__).resolve().parent / "static"


def list_seeds() -> list[dict]:
    rows = []
    for seed in SEEDS:
        rows.append(
            {
                "enquiry_id": seed["enquiry_id"],
                "company_name": seed["company_name"],
                "hard_case_type": seed.get("hard_case_type"),
                "label": f"{seed['enquiry_id']}  {seed['company_name']}"
                + (f"  ({seed['hard_case_type']})" if seed.get("hard_case_type") else ""),
            }
        )
    return rows


def evaluate_gates(enquiry: Enquiry, extraction: Extraction, scored, policy: dict) -> list[dict]:
    """Same order as route.py. First fired gate stops the chain."""
    phrases = policy["abstention"]["injection_phrases"]
    ood = {IntakeKind(item) for item in policy["abstention"]["ood_intake_kinds"]}
    kind = extraction.intake_kind.value if extraction.intake_kind.value else None
    owners = {item.owner for item in scored.line_scores}
    cross = len(scored.line_scores) >= 2 and len(owners) > 1
    proximity = bool(scored.competing_lines) and scored.line_scores and (
        scored.competing_lines[0].owner != scored.line_scores[0].owner
    )

    checks = [
        {
            "id": "empty",
            "title": "Empty description",
            "how": "Deterministic string check on the raw form field. No LLM.",
            "why": "There is nothing to extract. Routing would be invention.",
            "fired": not enquiry.description.strip(),
        },
        {
            "id": "injection",
            "title": "Instruction-like text in the enquiry",
            "how": "Substring match against policy.yaml injection_phrases, on the raw description.",
            "why": "A public form is untrusted. The model has no tool that can route. This tripwire catches the obvious case; unevidenced spans are also nulled.",
            "fired": _injection_hit(enquiry.description, phrases),
        },
        {
            "id": "ood",
            "title": "Out of taxonomy (vendor / job)",
            "how": "intake_kind from extraction, compared to policy ood_intake_kinds.",
            "why": "A pitch or a CV is not an engagement. Force-fitting it to a service line burns a lead.",
            "fired": kind in ood if kind is not None else False,
        },
        {
            "id": "low_evidence",
            "title": "Low evidence / null scoring drivers",
            "how": "Any null scoring driver (threshold 1 in policy.yaml), or no work signals.",
            "why": "Null is not zero. Unknown systems (+0 or +10h) can move 30h simple to 40h moderate.",
            "fired": (not scored.line_scores) or scored.low_evidence,
        },
        {
            "id": "cross_lead",
            "title": "Cross-lead conflict",
            "how": "Two or more scored lines whose owners differ. Hours gap does not matter.",
            "why": "Seed 11: strategy and regulatory belong to two humans. That is a policy question, not a model question.",
            "fired": cross,
        },
        {
            "id": "proximity",
            "title": "Hours proximity, different owner",
            "how": "Challenger within 15% of winner hours and a different lead.",
            "why": "Near-ties with two owners should not be auto-assigned.",
            "fired": bool(proximity),
        },
        {
            "id": "commit",
            "title": "Commit route from policy table",
            "how": "Winner service line maps to owner in policy.yaml. Same-lead overlap (seed 12) still commits.",
            "why": "Hours, tier, and route are defensible to a client only if they come from a file a partner can edit.",
            "fired": False,
        },
    ]

    stopped = False
    out = []
    for check in checks:
        if check["id"] == "commit":
            check["status"] = "fired" if not stopped else "not_reached"
            if not stopped:
                check["fired"] = True
            out.append(check)
            continue
        if stopped:
            check["status"] = "not_reached"
            out.append(check)
            continue
        if check["fired"]:
            check["status"] = "fired"
            stopped = True
        else:
            check["status"] = "passed"
        out.append(check)
    return out


def run_seed(enquiry_id: str, use_llm: bool = False) -> dict:
    seed = next(item for item in SEEDS if item["enquiry_id"] == enquiry_id)
    enquiry = seed_to_enquiry(seed)
    extraction_source = "authored_drivers"
    extraction = seed_to_extraction(seed)
    llm_error = None

    if use_llm:
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            llm_error = "ANTHROPIC_API_KEY is not set. Showing authored driver JSON, not a live model call."
        else:
            try:
                from intake_triage.extract import extract_with_llm

                extraction = extract_with_llm(enquiry.description, api_key=key)
                extraction_source = "live_llm"
            except Exception as exc:  # noqa: BLE001
                llm_error = str(exc)
                extraction = seed_to_extraction(seed)
                extraction_source = "authored_drivers_fallback"

    return _payload(enquiry, extraction, extraction_source, llm_error, seed.get("hard_case_type"))


def _payload(enquiry, extraction, extraction_source, llm_error, hard_case_type) -> dict:
    policy = load_policy()
    scored = score_extraction(extraction, enquiry, policy)
    decision = decide(enquiry, extraction, policy)
    gates = evaluate_gates(enquiry, extraction, scored, policy)
    lead = policy["leads"].get(decision.route_to, {}).get("name") if decision.route_to else None

    future_paths = [
        {
            "id": "now",
            "title": "Now (this prototype)",
            "detail": "Structured email to the lead or analyst, append-only spreadsheet row, JSONL decision log.",
        },
        {
            "id": "shadow",
            "title": "Week one",
            "detail": "Same writes, route nothing. Compare to the analyst. Adjudicate disagreements. That is the gold set.",
        },
        {
            "id": "webhook",
            "title": "If they keep the current form",
            "detail": "Assumption, not in the brief: Typeform webhook into a scale-to-zero function that calls extract then score then route.",
        },
        {
            "id": "crm",
            "title": "When they buy a CRM",
            "detail": "Import the JSONL. Field names are flat and stable. Do not start the CRM empty.",
        },
        {
            "id": "not_this",
            "title": "Not this journal",
            "detail": "This page is an interview walkthrough. Production is email plus a ledger. A four-lead firm will not maintain a queue app.",
        },
    ]

    return {
        "disclaimer": "Interview journal, not the production surface.",
        "extraction_source": extraction_source,
        "llm_error": llm_error,
        "hard_case_type": hard_case_type,
        "intake": {
            "enquiry_id": enquiry.enquiry_id,
            "company_name": enquiry.company_name,
            "contact_name": enquiry.contact_name,
            "industry": enquiry.industry.value,
            "company_size": enquiry.company_size.value,
            "urgency": enquiry.urgency.value,
            "submitted_at": enquiry.submitted_at.isoformat(),
            "description": enquiry.description,
        },
        "extraction": extraction.model_dump(mode="json"),
        "gates": gates,
        "provisional_lines": [item.model_dump(mode="json") for item in scored.line_scores],
        "null_drivers": scored.null_drivers,
        "rule_trace": decision.rule_trace,
        "decision": {
            "abstained": decision.abstained,
            "abstain_reason": decision.abstain_reason.value if decision.abstain_reason else None,
            "service_line": decision.service_line.value if decision.service_line else None,
            "complexity": decision.complexity.value if decision.complexity else None,
            "estimated_hours": decision.estimated_hours,
            "route_to": decision.route_to,
            "route_name": lead,
        },
        "output_json": decision.model_dump(mode="json"),
        "email": format_email(enquiry, decision, policy),
        "sheet_row": sheet_row(enquiry, decision),
        "future_paths": future_paths,
    }


def create_app():
    from fastapi import FastAPI
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    app = FastAPI(title="Intake triage journal")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "journal.html")

    @app.get("/api/seeds")
    def seeds():
        return {"seeds": list_seeds(), "has_llm_key": bool(os.environ.get("ANTHROPIC_API_KEY"))}

    @app.get("/api/run/{enquiry_id}")
    def run(enquiry_id: str, llm: bool = False):
        return run_seed(enquiry_id, use_llm=llm)

    return app


def main() -> None:
    import uvicorn

    uvicorn.run("intake_triage.journal:create_app", factory=True, host="127.0.0.1", port=8765, reload=False)


if __name__ == "__main__":
    main()
