"""Print the panel-critical routing paths. No LLM."""

from copy import deepcopy

from intake_triage.extract import validate_evidence_spans
from intake_triage.generate import seed_to_enquiry, seed_to_extraction
from intake_triage.pipeline import triage_from_extraction
from intake_triage.emit import format_email
from intake_triage.policy_loader import load_policy
from intake_triage.schema import Driver, Extraction, WorkSignal
from intake_triage.seeds import SEEDS


def _seed(eid: str) -> dict:
    return next(item for item in SEEDS if item["enquiry_id"] == eid)


def show(eid: str, note: str) -> None:
    seed = _seed(eid)
    enquiry = seed_to_enquiry(seed)
    decision = triage_from_extraction(enquiry, seed_to_extraction(seed))
    print("=" * 72)
    print(f"{eid}  {note}")
    print(f"  abstained={decision.abstained}  reason={decision.abstain_reason}")
    print(f"  line={decision.service_line}  hours={decision.estimated_hours}  tier={decision.complexity}")
    print(f"  route={decision.route_to}")
    if decision.competing_lines:
        for item in decision.competing_lines:
            print(f"  candidate {item.service_line.value} {item.hours}h -> {item.owner}")


def main() -> None:
    policy = load_policy()
    show("HG-2026-0001", "clean tax SIMPLE -> James")
    show("HG-2026-0002", "strategy 40h boundary MODERATE -> Priya")
    show("HG-2026-0003", "M&A 80h boundary COMPLEX -> James")
    show("HG-2026-0008", "stacked enterprise M&A 177h")
    show("HG-2026-0011", "MUST abstain: strategy + regulatory, different owners")
    show("HG-2026-0012", "MUST route James: M&A + tax, same owner")
    show("HG-2026-0015", "MUST abstain: prompt injection, never managing partner")

    seed = deepcopy(_seed("HG-2026-0001"))
    seed["extraction"]["systems_change"] = {"value": None, "evidence_span": None}
    d = triage_from_extraction(seed_to_enquiry(seed), seed_to_extraction(seed))
    print("=" * 72)
    print("null systems on otherwise-clean tax -> abstain (not 30h SIMPLE)")
    print(f"  abstained={d.abstained} hours={d.estimated_hours} route={d.route_to}")

    source = "Need a UK tax review for one company."
    checked, rejected = validate_evidence_spans(
        Extraction(work_signals=[Driver(value=WorkSignal.TAX, evidence_span="not in the source")]),
        source,
    )
    print("=" * 72)
    print("rejected evidence span drops the work signal")
    print(f"  rejected={rejected} remaining_signals={checked.work_signals}")

    print("=" * 72)
    print("sample email (0001)")
    print(format_email(seed_to_enquiry(_seed("HG-2026-0001")), triage_from_extraction(
        seed_to_enquiry(_seed("HG-2026-0001")),
        seed_to_extraction(_seed("HG-2026-0001")),
    ), policy))


if __name__ == "__main__":
    main()
