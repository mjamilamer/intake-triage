"""Nothing is dropped. Any failure becomes an abstention with an email and a JSON row.

The failure mode this exists to prevent is silent loss. An enquiry that cannot be
parsed, or that hits a model outage, must still reach a human, because the client
who sent it does not know anything went wrong and will not send it again.

Two rules:

1. A failure abstains to the analyst. It never guesses a lead and it never drops.
2. A failure is labelled `extraction_failed`, not `low_evidence`. Those look the
   same in a queue and mean opposite things: one is a terse letter that the system
   read correctly, the other is the system not having run. An analyst who cannot
   tell them apart cannot tell a bad week from an outage.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from intake_triage.emit import append_jsonl, format_email
from intake_triage.policy_loader import load_policy
from intake_triage.schema import (
    AbstainReason,
    Enquiry,
    Extraction,
    TriageDecision,
)

ROOT = Path(__file__).resolve().parent.parent
REVIEW_DIR = ROOT / "data" / "out" / "review"
DECISION_LOG = ROOT / "data" / "out" / "failsafe.jsonl"


def fallback_enquiry(row: dict, error: str) -> Enquiry:
    """Build a minimal Enquiry when the real one will not parse.

    The description is preserved verbatim even when every structured field is
    unusable, because the letter is the only thing a human actually needs.
    """
    return Enquiry(
        enquiry_id=str(row.get("enquiry_id") or "UNPARSEABLE"),
        submitted_at=datetime.now(timezone.utc),
        contact_name=None,
        contact_email=None,
        company_name=None,
        industry=None,
        company_size=None,
        urgency=None,
        description=str(row.get("description") or f"(no readable description: {error})"),
    )


def failsafe_decision(
    enquiry: Enquiry,
    error: str | BaseException,
    policy: dict | None = None,
    *,
    extraction: Extraction | None = None,
    stage: str = "extraction",
) -> TriageDecision:
    """Abstain to the analyst with the failure named. Never raises."""
    policy = policy or load_policy()
    detail = f"{type(error).__name__}: {error}" if isinstance(error, BaseException) else str(error)
    return TriageDecision(
        enquiry_id=enquiry.enquiry_id,
        service_line=None,
        complexity=None,
        estimated_hours=None,
        route_to=policy["analyst_email"],
        abstained=True,
        abstain_reason=AbstainReason.EXTRACTION_FAILED,
        competing_lines=[],
        rule_trace=[
            f"FAILSAFE: {stage} failed. This enquiry was not triaged.",
            f"CAUSE: {detail}",
            "ROUTED TO THE ANALYST UNCHANGED. Treat as untriaged, not as a low-evidence letter.",
        ],
        extraction=extraction or Extraction(),
        decided_at=datetime.now(timezone.utc),
    )


def emit_for_review(
    enquiry: Enquiry,
    decision: TriageDecision,
    policy: dict | None = None,
    *,
    review_dir: Path | None = None,
    log_path: Path | None = None,
) -> dict:
    """Write the email and the JSON a human reviews, and append the decision log.

    Best effort by design: a failure to write the review copy must not raise, or a
    disk problem would swallow the enquiry the failsafe exists to protect.
    """
    policy = policy or load_policy()
    target = review_dir or REVIEW_DIR
    written: dict[str, str] = {}
    try:
        email = format_email(enquiry, decision, policy)
    except Exception as exc:  # noqa: BLE001
        email = (
            f"To: {policy['analyst_email']}\n"
            f"Subject: FAILSAFE {enquiry.enquiry_id} needs manual triage\n\n"
            f"The formatter also failed ({type(exc).__name__}: {exc}).\n\n"
            f"{enquiry.description}\n"
        )
    try:
        target.mkdir(parents=True, exist_ok=True)
        email_path = target / f"{enquiry.enquiry_id}.email.txt"
        json_path = target / f"{enquiry.enquiry_id}.json"
        email_path.write_text(email, encoding="utf-8")
        json_path.write_text(
            json.dumps(decision.model_dump(mode="json"), indent=2), encoding="utf-8"
        )
        written["email"] = str(email_path)
        written["json"] = str(json_path)
    except OSError as exc:
        written["error"] = f"review copy not written: {exc}"
    try:
        append_jsonl(log_path or DECISION_LOG, decision)
        written["log"] = str(log_path or DECISION_LOG)
    except OSError as exc:
        written["log_error"] = str(exc)
    written["email_body"] = email
    return written


def handle_failure(
    row: dict | None,
    error: str | BaseException,
    *,
    enquiry: Enquiry | None = None,
    policy: dict | None = None,
    stage: str = "extraction",
    review_dir: Path | None = None,
    log_path: Path | None = None,
) -> tuple[Enquiry, TriageDecision, dict]:
    """One call for any failure path: decide, write the review copy, hand back both."""
    policy = policy or load_policy()
    subject = enquiry or fallback_enquiry(row or {}, str(error))
    decision = failsafe_decision(subject, error, policy, stage=stage)
    written = emit_for_review(
        subject, decision, policy, review_dir=review_dir, log_path=log_path
    )
    return subject, decision, written
