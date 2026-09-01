"""Interview journal. Teaching surface only. Production is the CLI against a CSV dump."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from intake_triage.emit import format_email, sheet_row
from intake_triage.generate import seed_to_enquiry, seed_to_extraction
from intake_triage.policy_loader import load_policy
from intake_triage.route import _injection_hit, decide
from intake_triage.schema import Enquiry, Extraction, IntakeKind
from intake_triage.score import score as score_extraction
from intake_triage.seeds import SEEDS
from intake_triage.journal_extras import (
    FREE_TEXT_IDS,
    HARD_IDS,
    JOURNAL_EXTRAS,
    LONG_IDS,
    VERY_HARD_IDS,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
ROOT = Path(__file__).resolve().parent.parent


def load_env_file() -> None:
    """Load repo .env. A non-empty value in the file wins so a blank shell var cannot block the key."""
    path = ROOT / ".env"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8-sig")
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("export "):
            line = line[7:].strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if not name or not value:
            continue
        os.environ[name] = value


def llm_status() -> dict:
    """Whether this process can call extract.py. Hint is the last four key characters."""
    load_env_file()
    key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    return {
        "has_llm_key": bool(key),
        "hint": f"…{key[-4:]}" if len(key) >= 8 else None,
    }

# Sixteen panel fixtures, then hard / very-hard extras, then two form-empty letters.
# The 50/150 batch stays in the terminal. Compare is left gold / right live.
INTERVIEW_IDS = [
    "HG-2026-0011",  # cross-lead hold
    "HG-2026-0012",  # same-lead overlap, routes
    "HG-2026-0015",  # injection hold
    "HG-2026-0001",  # easy tax
    "HG-2026-0002",  # strategy
    "HG-2026-0003",  # M&A complex
    "HG-2026-0004",  # Elena / risk
    "HG-2026-0005",  # David / tech
    "HG-2026-0016",  # vendor
    "HG-2026-0017",  # job
    "HG-2026-0022",  # generated easy, from the CSV
    "HG-2026-0041",  # generated medium
    "HG-2026-0049",  # generated cross-lead
    "HG-2026-0036",  # generated hard
    "HG-2026-0127",  # generated easy, named in the runbook
    "HG-2026-0010",  # Boreal, locked medium
    *HARD_IDS,
    *VERY_HARD_IDS,
    FREE_TEXT_IDS[0],
    FREE_TEXT_IDS[1],
]

TEST_IDS = [
    *INTERVIEW_IDS,
    *LONG_IDS,
    *FREE_TEXT_IDS,
]

CACHE_DIR = ROOT / "data" / "out" / "journal_cache"


def _cache_path(enquiry_id: str) -> Path:
    return CACHE_DIR / f"{enquiry_id}.json"


def load_cached(enquiry_id: str) -> dict | None:
    """Last compare or run for this id. Lives under data/out/journal_cache/."""
    path = _cache_path(enquiry_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def save_cached(enquiry_id: str, kind: str, payload: dict) -> None:
    """Persist a journal result. kind is 'compare' or legacy 'run'."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    body = {
        "kind": kind,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }
    _cache_path(enquiry_id).write_text(json.dumps(body, default=str), encoding="utf-8")


def cached_ids() -> list[str]:
    if not CACHE_DIR.exists():
        return []
    return sorted(path.stem for path in CACHE_DIR.glob("*.json"))

PANEL_IDS = {"HG-2026-0011", "HG-2026-0012", "HG-2026-0015"}
HELD_TYPES = {"two_word", "empty", "vendor_pitch", "job_applicant"}
WHY = {
    "ambiguous_cross_lead": "Strategy + regulatory, two owners",
    "same_lead_overlap": "M&A + tax, one owner",
    "prompt_injection": "Injection. Must hold.",
    "two_word": "Too thin to score",
    "empty": "Empty description",
    "vendor_pitch": "Vendor, not an enquiry",
    "job_applicant": "Job application",
    "implied_jurisdictions": "UK and Ireland implied",
    "relative_deadline": "Relative deadline",
    "duplicate_matter": "Looks like a duplicate",
    "journal_hard": "Dense drivers, still one letter.",
    "journal_very_hard": "Buried facts or three owners.",
    "journal_long": "The ask is after the background.",
    "journal_free_text": "Facts are in the letter.",
}


def _group(seed: dict) -> tuple[str, str]:
    kind = seed.get("hard_case_type")
    if seed["enquiry_id"] in PANEL_IDS or kind in {
        "ambiguous_cross_lead",
        "same_lead_overlap",
        "prompt_injection",
    }:
        return "panel", "Start here"
    if kind in HELD_TYPES:
        return "held", "Hold"
    if kind:
        return "edge", "Edge"
    return "clean", "Clean"


@lru_cache(maxsize=1)
def catalog() -> dict[str, dict]:
    """Locked seeds plus reverse-generated rows. Extraction stays in memory, not in the CSV."""
    from intake_triage.synth import assign_split, generate_records

    rows = assign_split(generate_records(150))
    extras = []
    for rec in JOURNAL_EXTRAS:
        row = dict(rec)
        row["split"] = "journal"
        extras.append(row)
    return {row["enquiry_id"]: row for row in list(rows) + extras}


def _card(rec: dict) -> dict:
    group, group_label = _group(rec)
    expected = rec.get("expected") or {}
    if expected.get("abstained"):
        outcome = "hold"
    else:
        outcome = expected.get("tier") or rec.get("difficulty") or "routed"
    kind = rec.get("hard_case_type")
    eid = rec["enquiry_id"]
    n = int(eid.split("-")[-1])
    form_empty = bool(rec.get("form_empty"))
    display = rec.get("list_title") or rec.get("company_name") or "Free-text enquiry"
    band = rec.get("difficulty") or ""
    why = WHY.get(kind) or ("CSV example" if n > 20 and n < 201 else "Straightforward")
    if band == "hard" and kind == "journal_hard":
        why = "Hard · " + why
    if band == "very_hard":
        why = "Very hard · " + why.replace("Very hard. ", "")
    if kind == "journal_long":
        why = "Long prompt · " + why
    if form_empty:
        why = "No form fields · " + why
    return {
        "enquiry_id": eid,
        "company_name": display,
        "hard_case_type": kind,
        "group": group,
        "group_label": group_label,
        "why": why,
        "outcome": outcome,
        "difficulty": band,
        "split": rec.get("split") or "",
        "source": "locked" if n <= 20 else ("journal" if rec.get("split") == "journal" else "generated"),
        "interview": eid in INTERVIEW_IDS,
        "form_empty": form_empty,
    }


def list_seeds() -> list[dict]:
    """The 20 locked fixtures. Kept for tests and the offline path."""
    return [_card(seed) for seed in SEEDS]


def list_cases(pack: str = "interview") -> list[dict]:
    """Cases for Interview, Test, Call 50, or All 150. Journal extras are not in the CSVs."""
    records = catalog()
    if pack == "interview":
        return [_card(records[eid]) for eid in INTERVIEW_IDS if eid in records]
    if pack == "test":
        seen = set()
        out = []
        for eid in TEST_IDS:
            if eid in records and eid not in seen:
                out.append(_card(records[eid]))
                seen.add(eid)
        return out
    if pack == "call":
        rows = [_card(r) for r in records.values() if r.get("split") == "call"]
        order = {eid: i for i, eid in enumerate(INTERVIEW_IDS)}
        rows.sort(
            key=lambda c: (
                0 if c["enquiry_id"] in order else 1,
                order.get(c["enquiry_id"], 99),
                c["enquiry_id"],
            )
        )
        return rows
    rows = [_card(r) for r in records.values() if r.get("split") != "journal"]
    rows.sort(key=lambda c: c["enquiry_id"])
    return rows


def pack_counts() -> dict[str, int]:
    records = catalog()
    return {
        "interview": sum(1 for eid in INTERVIEW_IDS if eid in records),
        "test": len({eid for eid in TEST_IDS if eid in records}),
        "call": sum(1 for r in records.values() if r.get("split") == "call"),
        "all": sum(1 for r in records.values() if r.get("split") != "journal"),
    }


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
            "id": "cross_lead",
            "title": "Cross-lead conflict",
            "how": "Two or more scored lines whose owners differ. Hours gap does not matter. Checked before low-evidence so a named second ask is not hidden by a silent deadline.",
            "why": "The letter can be fully evidenced and still hold. Seed 11 quotes an operating-model ask and a PRA review. Priya owns one; Elena owns the other. Policy will not pick a lead.",
            "fired": cross,
        },
        {
            "id": "low_evidence",
            "title": "Low evidence / material unknown",
            "how": (
                "An unknown driver blocks a committed tier only when filling it in could "
                "move the hours across a tier boundary. The null-count in policy.yaml is a "
                "backstop for letters too sparse to triage (threshold 4)."
                + (f" Null now: {', '.join(scored.null_drivers)}." if scored.null_drivers else "")
            ),
            "why": "Null is not zero. Unknown systems on a 30h tax can reach 40h moderate, so that holds. The same unknown on an 80h M&A cannot leave complex, so that commits and the email says the hours omit it.",
            "fired": (not scored.line_scores) or scored.low_evidence,
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


def intake_card(enquiry_id: str) -> dict:
    """Form text and picklists only. No extraction JSON. Restores the last compare if cached."""
    rec = catalog().get(enquiry_id)
    if rec is None:
        raise KeyError(f"No enquiry {enquiry_id}")
    enquiry = seed_to_enquiry(rec)
    card = _card(rec)
    form = {
        "company_name": enquiry.company_name,
        "industry": enquiry.industry.value if enquiry.industry else None,
        "company_size": enquiry.company_size.value if enquiry.company_size else None,
        "urgency": enquiry.urgency.value if enquiry.urgency else None,
        "contact_name": enquiry.contact_name,
    }
    filled = {key: value for key, value in form.items() if value}
    last = load_cached(enquiry_id)
    return {
        **card,
        "contact_name": enquiry.contact_name,
        "industry": form["industry"],
        "company_size": form["company_size"],
        "urgency": form["urgency"],
        "submitted_at": enquiry.submitted_at.isoformat(),
        "description": enquiry.description,
        "form": form,
        "form_filled": filled,
        "form_empty": bool(rec.get("form_empty")) or not filled,
        "last": last,
        "has_last": last is not None,
    }


def run_compare(enquiry_id: str) -> dict:
    """Deterministic gold on the left, live LLM extract on the right."""
    before = run_seed(enquiry_id, use_llm=False)
    after = run_seed(enquiry_id, use_llm=True)
    b, a = before["decision"], after["decision"]
    keys = ("abstained", "abstain_reason", "service_line", "complexity", "estimated_hours", "route_to")
    result = {
        "before": before,
        "after": after,
        "same_route": all(b.get(k) == a.get(k) for k in keys),
        "llm_status": llm_status(),
    }
    return result


def decision_brief(payload: dict) -> dict:
    d = payload["decision"]
    return {
        "abstained": d["abstained"],
        "label": (
            f"Abstain · {d['abstain_reason']}"
            if d["abstained"]
            else f"{d['complexity']} · {d['estimated_hours']}h"
        ),
        "route": d.get("route_name") or d.get("route_to"),
        "line": d.get("service_line"),
    }


def run_seed(enquiry_id: str, use_llm: bool = False) -> dict:
    """Score one journal case. use_llm=False is gold drivers. use_llm=True is a live extract."""
    rec = catalog().get(enquiry_id)
    if rec is None:
        rec = next((item for item in SEEDS if item["enquiry_id"] == enquiry_id), None)
    if rec is None:
        raise KeyError(f"No enquiry {enquiry_id}")

    enquiry = seed_to_enquiry(rec)
    n = int(enquiry_id.split("-")[-1])
    if rec.get("split") == "journal":
        record_source = "journal"
        extraction_source = "authored_drivers"
    elif n <= 20:
        record_source = "locked"
        extraction_source = "authored_drivers"
    else:
        record_source = "generated"
        extraction_source = "reverse_generated"
    extraction = seed_to_extraction(rec)
    llm_error = None

    if use_llm:
        load_env_file()
        key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
        if not key:
            llm_error = "ANTHROPIC_API_KEY is not set. Put it in .env and restart the journal."
            extraction = Extraction()
            extraction_source = "failed"
        else:
            try:
                from intake_triage.extract import extract_with_llm

                extraction = extract_with_llm(enquiry.description, api_key=key)
                extraction_source = "live_llm"
            except Exception as exc:  # noqa: BLE001
                llm_error = str(exc)
                extraction = Extraction()
                extraction_source = "failed"

    payload = _payload(enquiry, extraction, extraction_source, llm_error, rec.get("hard_case_type"))
    payload["record_source"] = record_source
    payload["llm_status"] = llm_status()
    payload["form_empty"] = bool(rec.get("form_empty"))
    return payload


def _payload(enquiry, extraction, extraction_source, llm_error, hard_case_type) -> dict:
    """Journal JSON for one column: decision, gates, email, sheet row."""
    policy = load_policy()
    if extraction_source == "failed":
        from intake_triage.failsafe import failsafe_decision

        decision = failsafe_decision(
            enquiry, llm_error or "extraction failed", policy, stage="extraction"
        )
        gates = [
            {
                "id": "extraction_failed",
                "title": "Extraction did not run",
                "how": "The model call failed, or no API key was present. Nothing was scored.",
                "why": "An outage is not a terse letter. The analyst must see extraction_failed, not low_evidence.",
                "fired": True,
                "status": "fired",
            }
        ]
        lead = policy["leads"].get(decision.route_to, {}).get("name") if decision.route_to else None
        return {
            "disclaimer": "Interview journal, not the production surface.",
            "extraction_source": extraction_source,
            "llm_error": llm_error,
            "hard_case_type": hard_case_type,
            "intake": {
                "enquiry_id": enquiry.enquiry_id,
                "company_name": enquiry.company_name,
                "contact_name": enquiry.contact_name,
                "industry": enquiry.industry.value if enquiry.industry else None,
                "company_size": enquiry.company_size.value if enquiry.company_size else None,
                "urgency": enquiry.urgency.value if enquiry.urgency else None,
                "submitted_at": enquiry.submitted_at.isoformat(),
                "description": enquiry.description,
            },
            "extraction": extraction.model_dump(mode="json"),
            "gates": gates,
            "provisional_lines": [],
            "null_drivers": [],
            "rule_trace": decision.rule_trace,
            "decision": {
                "abstained": decision.abstained,
                "abstain_reason": decision.abstain_reason.value if decision.abstain_reason else None,
                "service_line": None,
                "complexity": None,
                "estimated_hours": None,
                "route_to": decision.route_to,
                "route_name": lead,
            },
            "output_json": decision.model_dump(mode="json"),
            "email": format_email(enquiry, decision, policy),
            "sheet_row": sheet_row(enquiry, decision),
            "future_paths": [],
        }

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
            "detail": "This page is an interview walkthrough of one enquiry. Production is a CSV dump walked by python -m intake_triage run. A four-lead firm will not maintain a queue app.",
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
            "industry": enquiry.industry.value if enquiry.industry else None,
            "company_size": enquiry.company_size.value if enquiry.company_size else None,
            "urgency": enquiry.urgency.value if enquiry.urgency else None,
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
    """FastAPI app. HTML is FileResponse so a refresh picks up journal.html."""
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel

    load_env_file()

    class KeyBody(BaseModel):
        key: str

    app = FastAPI(title="Intake triage journal")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "journal.html")

    @app.get("/api/status")
    def status():
        return llm_status()

    @app.post("/api/session-key")
    def session_key(body: KeyBody):
        key = body.key.strip()
        if not key:
            raise HTTPException(status_code=400, detail="Empty key")
        os.environ["ANTHROPIC_API_KEY"] = key
        return llm_status()

    @app.get("/api/seeds")
    def seeds():
        return {"seeds": list_seeds(), **llm_status()}

    @app.get("/api/cases")
    def cases(pack: str = "interview"):
        if pack not in {"interview", "test", "call", "all"}:
            pack = "interview"
        source = pack
        return {
            "pack": pack,
            "packs": pack_counts(),
            "cached_ids": cached_ids(),
            "cases": list_cases(pack),
            **llm_status(),
        }

    @app.get("/api/intake/{enquiry_id}")
    def intake(enquiry_id: str):
        try:
            return intake_card(enquiry_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/run/{enquiry_id}")
    def run(enquiry_id: str, llm: bool = False):
        try:
            payload = run_seed(enquiry_id, use_llm=llm)
            if llm:
                save_cached(enquiry_id, "run", payload)
            return payload
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/compare/{enquiry_id}")
    def compare(enquiry_id: str):
        try:
            result = run_compare(enquiry_id)
            save_cached(enquiry_id, "compare", result)
            return result
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return app


def main() -> None:
    import uvicorn

    load_env_file()
    uvicorn.run("intake_triage.journal:create_app", factory=True, host="127.0.0.1", port=8765, reload=False)


if __name__ == "__main__":
    main()
