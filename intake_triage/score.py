"""Hours, tier, and competing lines. No LLM. Null is omitted, not treated as zero."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from intake_triage.policy_loader import load_policy
from intake_triage.schema import (
    CompanySize,
    ComplexityTier,
    DeadlineKind,
    Driver,
    Enquiry,
    Extraction,
    LineScore,
    ScoreResult,
    ServiceLine,
    WorkSignal,
)


def round_half_up(value: float) -> int:
    """Banker's-round-away-from-even: 0.5 goes up. Matches the written formula."""
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _driver_null(driver: Driver | None) -> bool:
    if driver is None:
        return True
    return driver.value is None


def _span(driver: Driver | None) -> str | None:
    if driver is None:
        return None
    return driver.evidence_span


def score(extraction: Extraction, enquiry: Enquiry, policy: dict | None = None) -> ScoreResult:
    """Turn evidenced facts into provisional hours. A committed tier needs every scoring driver."""
    policy = policy or load_policy()
    trace: list[str] = []
    null_drivers: list[str] = []

    signals = [item for item in extraction.work_signals if item.value is not None]
    if not signals:
        null_drivers.append("work_signals")
        trace.append("NULL: work signals not determinable from text")

    jurs = extraction.jurisdiction_names
    if _driver_null(jurs) or not jurs.value:
        null_drivers.append("jurisdiction_names")
        trace.append("NULL: jurisdictions not determinable from text")
        extra_jurs = 0  # omitted from committed score; see low_evidence
        jur_span = None
    else:
        extra_jurs = max(len(jurs.value) - 1, 0)
        jur_span = _span(jurs)

    entities = extraction.entity_count
    if _driver_null(entities):
        null_drivers.append("entity_count")
        trace.append("NULL: entity count not determinable from text")
        extra_entities = 0  # omitted from committed score; see low_evidence
    else:
        extra_entities = max(int(entities.value) - 1, 0)

    workstreams = extraction.workstream_count
    if _driver_null(workstreams):
        null_drivers.append("workstream_count")
        trace.append("NULL: workstreams not determinable from text")
        extra_ws = 0  # omitted from committed score; see low_evidence
    else:
        extra_ws = max(int(workstreams.value) - 1, 0)

    deadline = extraction.deadline_kind
    if _driver_null(deadline):
        null_drivers.append("deadline_kind")
        trace.append("NULL: deadline kind not determinable from text")
        deadline_mult = 1.0  # omitted unknown; committed score abstains
        hard = False
    else:
        hard = deadline.value == DeadlineKind.HARD
        deadline_mult = float(policy["multipliers"]["hard_deadline"]) if hard else 1.0

    regulator = extraction.regulator_or_investigation
    if _driver_null(regulator):
        null_drivers.append("regulator_or_investigation")
        trace.append("NULL: regulator or investigation pressure not determinable from text")
        regulator_on = False  # unknown is not "no regulator"
    else:
        regulator_on = bool(regulator.value)

    systems = extraction.systems_change
    if _driver_null(systems):
        null_drivers.append("systems_change")
        trace.append("NULL: systems change not determinable from text")
        systems_on = False  # unknown is not "no systems change"
    else:
        systems_on = bool(systems.value)

    multi = extraction.multi_party
    if _driver_null(multi):
        null_drivers.append("multi_party")
        trace.append("NULL: multi-party involvement not determinable from text")
        multi_on = False  # unknown is not "single party"
    else:
        multi_on = bool(multi.value)

    # Unknown modifiers are omitted from the hour arithmetic. That number is
    # provisional only. A committed tier requires every scoring driver present
    # (policy abstention.low_evidence_null_threshold, currently 1).
    adds = policy["additives"]
    additive = 0
    additive += extra_jurs * int(adds["extra_jurisdiction_hours"])
    additive += extra_entities * int(adds["extra_entity_hours"])
    additive += extra_ws * int(adds["extra_workstream_hours"])
    if regulator_on:
        additive += int(adds["regulator_or_investigation_hours"])
    if systems_on:
        additive += int(adds["systems_change_hours"])
    if multi_on:
        additive += int(adds["multi_party_hours"])

    size = enquiry.company_size
    if size is None:
        stated_size = extraction.stated_company_size
        if _driver_null(stated_size):
            null_drivers.append("company_size")
            trace.append("NULL: company size not on the form and not determinable from text")
            size_mult = 1.0
        else:
            size = CompanySize(stated_size.value)
            size_mult = float(policy["multipliers"]["company_size"][size.value])
            if stated_size.evidence_span:
                trace.append(
                    f"SIZE FROM TEXT: {size.value} (evidence: '{stated_size.evidence_span}')"
                )
    else:
        size_mult = float(policy["multipliers"]["company_size"][size.value])

    threshold = int(policy["abstention"]["low_evidence_null_threshold"])
    low_evidence = len(null_drivers) >= threshold or not signals

    signal_map: dict[WorkSignal, ServiceLine] = {
        WorkSignal(key): ServiceLine(value) for key, value in policy["work_signal_map"].items()
    }

    line_scores: list[LineScore] = []
    for signal in signals:
        line = signal_map[signal.value]
        spec = policy["service_lines"][line.value]
        base = int(spec["base_hours"])
        raw = (base + additive) * deadline_mult * size_mult
        hours = round_half_up(raw)
        spans = [s for s in [signal.evidence_span, jur_span] if s]
        line_trace = [f"Base: {line.value} {base}h"]
        if extra_jurs:
            line_trace.append(
                f"+{extra_jurs * adds['extra_jurisdiction_hours']}h: {extra_jurs + 1} named locations"
                + (f" (evidence: '{jur_span}')" if jur_span else "")
            )
        if extra_entities:
            span = _span(entities)
            line_trace.append(
                f"+{extra_entities * adds['extra_entity_hours']}h: {entities.value} entities"
                + (f" (evidence: '{span}')" if span else "")
            )
        if extra_ws:
            span = _span(workstreams)
            line_trace.append(
                f"+{extra_ws * adds['extra_workstream_hours']}h: {workstreams.value} workstreams"
                + (f" (evidence: '{span}')" if span else "")
            )
        if regulator_on:
            span = _span(regulator)
            line_trace.append(
                "+{h}h: regulator or investigation".format(h=adds["regulator_or_investigation_hours"])
                + (f" (evidence: '{span}')" if span else "")
            )
        if systems_on:
            span = _span(systems)
            line_trace.append(
                "+{h}h: systems change".format(h=adds["systems_change_hours"])
                + (f" (evidence: '{span}')" if span else "")
            )
        if multi_on:
            span = _span(multi)
            line_trace.append(
                "+{h}h: multiple parties".format(h=adds["multi_party_hours"])
                + (f" (evidence: '{span}')" if span else "")
            )
        if hard:
            span = _span(deadline)
            line_trace.append(
                f"x{policy['multipliers']['hard_deadline']}: hard deadline"
                + (f" (evidence: '{span}')" if span else "")
            )
        if size is not None and size != CompanySize.SME:
            line_trace.append(f"x{size_mult}: company size {size.value}")
        line_trace.append(f"Result: {hours}h -> {tier_for(hours, policy).value.upper()}")
        line_scores.append(
            LineScore(
                service_line=line,
                hours=hours,
                owner=spec["owner"],
                evidence_spans=spans,
            )
        )
        trace.extend(line_trace)

    if null_drivers:
        trace.append(
            "PROVISIONAL: unknown drivers omitted from hours; no committed tier until they are present"
        )

    if not line_scores:
        return ScoreResult(
            estimated_hours=None,
            complexity=None,
            service_line=None,
            rule_trace=trace,
            competing_lines=[],
            line_scores=[],
            null_drivers=null_drivers,
            low_evidence=True,
        )

    ranked = sorted(line_scores, key=lambda item: item.hours, reverse=True)
    winner = ranked[0]
    proximity = float(policy["abstention"]["competing_hours_pct"])
    competing = [
        item
        for item in ranked[1:]
        if winner.hours > 0 and abs(item.hours - winner.hours) / winner.hours <= proximity
    ]
    committed = not low_evidence
    return ScoreResult(
        estimated_hours=winner.hours if committed else None,
        complexity=tier_for(winner.hours, policy) if committed else None,
        service_line=winner.service_line if committed else None,
        rule_trace=trace,
        competing_lines=competing,
        line_scores=ranked,
        null_drivers=null_drivers,
        low_evidence=low_evidence,
    )


def tier_for(hours: int, policy: dict) -> ComplexityTier:
    """Simple < 40. Moderate 40 inclusive to < 80. Complex >= 80."""
    simple_max = int(policy["tiers"]["simple_max_exclusive"])
    moderate_max = int(policy["tiers"]["moderate_max_exclusive"])
    # 40 is inclusive on moderate. 80 is inclusive on complex.
    if hours < simple_max:
        return ComplexityTier.SIMPLE
    if hours < moderate_max:
        return ComplexityTier.MODERATE
    return ComplexityTier.COMPLEX
