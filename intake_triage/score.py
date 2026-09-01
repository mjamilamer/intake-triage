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
        deadline_mult = 1.0  # omitted unknown; materiality test below decides
        hard = False
    else:
        hard = deadline.value == DeadlineKind.HARD
        deadline_mult = float(policy["multipliers"]["hard_deadline"]) if hard else 1.0

    # Escalating-factor booleans. Unknown is not "no regulator": the hour arithmetic
    # omits it, and the materiality test below decides whether that omission could
    # change the tier. Silence is never quietly scored as a negative.
    def _flag(field: str, label: str) -> tuple[bool, Driver | None, bool]:
        """Returns (value_now, driver, unknown)."""
        driver = getattr(extraction, field)
        if not _driver_null(driver):
            return bool(driver.value), driver, False
        null_drivers.append(field)
        trace.append(f"NULL: {label} not determinable from text")
        return False, driver, True

    regulator_on, regulator, regulator_unknown = _flag(
        "regulator_or_investigation", "regulator or investigation pressure"
    )
    systems_on, systems, systems_unknown = _flag("systems_change", "systems change")
    multi_on, multi, multi_unknown = _flag("multi_party", "multi-party involvement")

    # Unknown modifiers are omitted from the hour arithmetic. That number is
    # the floor. Materiality below decides whether the omission can change the
    # tier. A committed route is allowed only when the worst case stays put.
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

    # Worst case: every open-world unknown takes its escalating value. Compared
    # against the committed number below to decide whether the unknown is material.
    ceiling = int(policy["abstention"].get("unstated_count_ceiling", 2))
    additive_max = additive
    if "jurisdiction_names" in null_drivers:
        additive_max += max(ceiling - 1, 0) * int(adds["extra_jurisdiction_hours"])
    if "entity_count" in null_drivers:
        additive_max += max(ceiling - 1, 0) * int(adds["extra_entity_hours"])
    if "workstream_count" in null_drivers:
        additive_max += max(ceiling - 1, 0) * int(adds["extra_workstream_hours"])
    if regulator_unknown:
        additive_max += int(adds["regulator_or_investigation_hours"])
    if systems_unknown:
        additive_max += int(adds["systems_change_hours"])
    if multi_unknown:
        additive_max += int(adds["multi_party_hours"])

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

    hard_mult = float(policy["multipliers"]["hard_deadline"])
    deadline_mult_max = hard_mult if "deadline_kind" in null_drivers else deadline_mult
    size_mult_max = size_mult
    if "company_size" in null_drivers:
        size_mult_max = max(float(v) for v in policy["multipliers"]["company_size"].values())

    # A letter this sparse is not a triage problem, it is an incomplete enquiry.
    # The threshold is a backstop for those, not the primary abstention rule.
    threshold = int(policy["abstention"]["low_evidence_null_threshold"])
    too_sparse = len(null_drivers) >= threshold
    low_evidence = not signals

    signal_map: dict[WorkSignal, ServiceLine] = {
        WorkSignal(key): ServiceLine(value) for key, value in policy["work_signal_map"].items()
    }

    line_scores: list[LineScore] = []
    hours_max: dict[ServiceLine, int] = {}
    for signal in signals:
        line = signal_map[signal.value]
        spec = policy["service_lines"][line.value]
        base = int(spec["base_hours"])
        raw = (base + additive) * deadline_mult * size_mult
        hours = round_half_up(raw)
        hours_max[line] = round_half_up((base + additive_max) * deadline_mult_max * size_mult_max)
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
    # Materiality. An unknown only blocks a committed tier if knowing it could move
    # the answer across a tier boundary. A missing systems flag on a 30h matter can
    # reach 40h and flip simple to moderate, so that abstains. The same missing flag
    # on a 95h matter cannot leave complex, so it commits and says what it assumed.
    worst = hours_max.get(winner.service_line, winner.hours)
    committed_tier = tier_for(winner.hours, policy)
    worst_tier = tier_for(worst, policy)
    if null_drivers and worst_tier is not committed_tier:
        low_evidence = True
        trace.append(
            "PROVISIONAL: MATERIAL UNKNOWN: "
            + ", ".join(null_drivers)
            + f" could move {winner.hours}h ({committed_tier.value}) to "
            + f"{worst}h ({worst_tier.value}). No committed tier."
        )
    elif null_drivers and too_sparse:
        low_evidence = True
        trace.append(
            f"PROVISIONAL: TOO SPARSE: {len(null_drivers)} unknown drivers "
            + f"({', '.join(null_drivers)}). Incomplete enquiry, not a triage decision."
        )
    elif null_drivers:
        trace.append(
            "IMMATERIAL UNKNOWN: "
            + ", ".join(null_drivers)
            + f" unknown, but worst case {worst}h stays {committed_tier.value}. Committed."
        )

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
