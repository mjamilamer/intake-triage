from __future__ import annotations

from datetime import datetime, timezone

from intake_triage.policy_loader import load_policy
from intake_triage.schema import (
    AbstainReason,
    Enquiry,
    Extraction,
    IntakeKind,
    ScoreResult,
    TriageDecision,
)
from intake_triage.score import score as score_extraction


def _injection_hit(text: str, phrases: list[str]) -> bool:
    lowered = text.lower()
    return any(phrase.lower() in lowered for phrase in phrases)


def route(
    score_result: ScoreResult,
    enquiry: Enquiry,
    extraction: Extraction,
    policy: dict | None = None,
    *,
    model_version: str | None = None,
    prompt_version: str | None = None,
    samples: int = 1,
    latency_ms: int | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
) -> TriageDecision:
    policy = policy or load_policy()
    decided_at = datetime.now(timezone.utc)
    trace = list(score_result.rule_trace)
    competing = list(score_result.line_scores[:2]) if score_result.line_scores else []

    def abstain(reason: AbstainReason, extra: str) -> TriageDecision:
        trace.append(extra)
        return TriageDecision(
            enquiry_id=enquiry.enquiry_id,
            service_line=None,
            complexity=None,
            estimated_hours=None,
            route_to=policy["analyst_email"],
            abstained=True,
            abstain_reason=reason,
            competing_lines=competing,
            rule_trace=trace,
            extraction=extraction,
            model_version=model_version,
            prompt_version=prompt_version,
            samples=samples,
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            decided_at=decided_at,
        )

    if not enquiry.description.strip():
        return abstain(
            AbstainReason.OUT_OF_TAXONOMY,
            "ABSTAIN: empty description (out of taxonomy)",
        )

    if _injection_hit(enquiry.description, policy["abstention"]["injection_phrases"]):
        return abstain(
            AbstainReason.OUT_OF_TAXONOMY,
            "ABSTAIN: instruction-like text in the enquiry treated as data, not followed",
        )

    kind = extraction.intake_kind.value if extraction.intake_kind.value else None
    ood = {IntakeKind(item) for item in policy["abstention"]["ood_intake_kinds"]}
    if kind in ood:
        return abstain(
            AbstainReason.OUT_OF_TAXONOMY,
            f"ABSTAIN: intake_kind={kind.value} is out of taxonomy",
        )

    if not score_result.line_scores or score_result.low_evidence:
        return abstain(
            AbstainReason.LOW_EVIDENCE,
            "ABSTAIN: low evidence (missing work signals or too many null drivers)",
        )

    owners = {item.owner for item in score_result.line_scores}
    if len(score_result.line_scores) >= 2 and len(owners) > 1:
        names = ", ".join(
            f"{item.service_line.value} {item.hours}h -> {item.owner}"
            for item in score_result.line_scores[:2]
        )
        return abstain(
            AbstainReason.CROSS_LEAD_CONFLICT,
            f"ABSTAIN: cross-lead conflict ({names})",
        )

    if score_result.competing_lines:
        challenger = score_result.competing_lines[0]
        winner = score_result.line_scores[0]
        if challenger.owner != winner.owner:
            return abstain(
                AbstainReason.HOURS_PROXIMITY,
                "ABSTAIN: competing line within 15% of winner hours and different owner",
            )

    winner = score_result.line_scores[0]
    if len(score_result.line_scores) >= 2:
        second = score_result.line_scores[1]
        if second.owner == winner.owner:
            trace.append(
                f"SAME-LEAD OVERLAP: also {second.service_line.value} {second.hours}h; "
                f"routed to dual owner {winner.owner}"
            )

    trace.append(f"ROUTE: {winner.service_line.value} -> {winner.owner}")
    return TriageDecision(
        enquiry_id=enquiry.enquiry_id,
        service_line=winner.service_line,
        complexity=score_result.complexity,
        estimated_hours=score_result.estimated_hours,
        route_to=winner.owner,
        abstained=False,
        abstain_reason=None,
        competing_lines=score_result.line_scores[1:2],
        rule_trace=trace,
        extraction=extraction,
        model_version=model_version,
        prompt_version=prompt_version,
        samples=samples,
        latency_ms=latency_ms,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        decided_at=decided_at,
    )


def decide(enquiry: Enquiry, extraction: Extraction, policy: dict | None = None) -> TriageDecision:
    policy = policy or load_policy()
    scored = score_extraction(extraction, enquiry, policy)
    return route(scored, enquiry, extraction, policy)
