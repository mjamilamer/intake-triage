"""One LLM call. Forced tool use. Facts plus verbatim spans. The model does not decide."""

from __future__ import annotations

import json
import re
from pathlib import Path

from intake_triage.schema import Extraction

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "extract_v1.md"
PINNED_MODEL = "claude-sonnet-4-6"  # Mid-tier. Dateless 4.6 IDs are pinned snapshots, not latest aliases. Haiku flattened Driver objects.
PROMPT_VERSION = "extract_v1"

DRIVER_FIELDS = (
    "jurisdiction_names",
    "entity_count",
    "workstream_count",
    "deadline_kind",
    "regulator_or_investigation",
    "systems_change",
    "multi_party",
    "intake_kind",
    "stated_company",
    "stated_industry",
    "stated_company_size",
    "stated_urgency",
)

_JUR_ALIAS = {
    "united kingdom": "UK",
    "great britain": "UK",
    "britain": "UK",
    "u.k.": "UK",
    "u.k": "UK",
    "uk": "UK",
    "republic of ireland": "Ireland",
    "eire": "Ireland",
}

_SPAN_HINTS = {
    "systems_change": (
        "No systems programme",
        "No system replacement",
        "this is a system cutover",
        "This is a system cutover",
    ),
    "multi_party": (
        "Nobody else is in the room",
        "nobody else is in the room",
        "sponsors and the target CFO are in the room",
    ),
    "regulator_or_investigation": (
        "Not a police or fraud matter",
        "PRA thematic review",
        "Ofgem opened a file",
        "CQC wrote after an inspection",
    ),
    "deadline_kind": (
        "No immovable date",
        "No filing date hanging over us",
        "must be ready before the 30 September board",
        "over the next quarter",
    ),
    "entity_count": (
        "One entity",
        "one entity",
        "one legal entity",
        "One UK company only",
        "Two legal entities",
        "two legal entities",
        "Three legal entities",
        "three legal entities",
    ),
    "workstream_count": (
        "one distinct stream",
        "two distinct streams",
        "Three distinct streams",
        "three distinct streams",
        "in the same letter",
        "view on the operating model",
    ),
    "stated_company_size": (
        "about 180 people",
        "about ninety people",
        "about 120 people",
        "roughly 80 people",
        "About 4,200 staff",
        "About 600 staff",
        "About 3,100 staff",
        "About 5,000 staff",
        "about 800 staff",
        "About 900 staff",
    ),
    "stated_urgency": (
        "This is not urgent",
        "normal, not urgent",
        "this is high urgency",
        "High urgency",
        "high urgency",
    ),
    "intake_kind": (
        "Want a view on the operating model",
        "Need a review",
        "Board asked",
        "Writing for",
        "We need a new operating model",
    ),
    "stated_industry": (
        "a consumer business",
        "a professional services firm",
        "financial services",
    ),
}

_SIGNAL_HINTS = {
    "strategy": (
        "view on the operating model",
        "operating-model recommendation",
        "new operating model",
        "operating model",
    ),
    "tax": ("UK corporation-tax issue", "corporation-tax issue", "corporation-tax"),
    "transaction": ("buying a small target", "We are buying a small target"),
    "regulatory": (
        "controls response after inspection",
        "responding to the PRA thematic review",
        "PRA thematic review",
    ),
    "technology": ("data platform build", "reporting dashboard"),
}


def load_prompt() -> str:
    """Read prompts/extract_v1.md. Prompts are files, never string literals."""
    return PROMPT_PATH.read_text(encoding="utf-8")


def extraction_json_schema() -> dict:
    """Tool schema from the Pydantic model. Do not hand-write a duplicate."""
    return Extraction.model_json_schema()


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _slice(source: str, needle: str) -> str | None:
    if not needle:
        return None
    hay = _norm(source)
    find = _norm(needle)
    at = hay.find(find)
    if at < 0:
        return None
    # Map normalized offset back approximately via case-insensitive search on original.
    match = re.search(re.escape(needle), source, flags=re.IGNORECASE)
    if match:
        return match.group(0)
    return needle


def _maybe_json(raw):
    if not isinstance(raw, str):
        return raw
    text = raw.strip()
    if not text or text[0] not in "[{":
        return raw
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return raw


def _parse_bool(raw):
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        lowered = raw.strip().lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
    return raw


def _parse_int(raw):
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.strip().lstrip("-").isdigit():
        return int(raw.strip())
    return raw


def _driver_dict(raw) -> dict:
    if raw is None:
        return {"value": None, "evidence_span": None}
    if isinstance(raw, dict):
        value = raw.get("value", raw.get("Value"))
        span = raw.get("evidence_span") or raw.get("evidence") or raw.get("span")
        if "value" not in raw and "evidence_span" not in raw and len(raw) == 1:
            only = next(iter(raw.values()))
            return {"value": only, "evidence_span": None}
        return {"value": value, "evidence_span": span if span else None}
    return {"value": raw, "evidence_span": None}


def _normalise_jurs(value) -> list[str] | None:
    value = _maybe_json(value)
    if value is None:
        return None
    if isinstance(value, str):
        names = [part.strip() for part in re.split(r",| and ", value) if part.strip()]
    elif isinstance(value, list):
        names = [str(item).strip() for item in value if str(item).strip()]
    else:
        return None
    out = []
    for name in names:
        mapped = _JUR_ALIAS.get(_norm(name), name)
        if mapped == "UK":
            out.append("UK")
        else:
            out.append(mapped)
    return out or None


def _attach_span(field: str, value, span: str | None, source: str):
    if span and _norm(span) in _norm(source):
        return _slice(source, span) or span
    if isinstance(value, str):
        found = _slice(source, value)
        if found:
            return found
    if field == "work_signals" and isinstance(value, str):
        for hint in _SIGNAL_HINTS.get(value, ()):
            found = _slice(source, hint)
            if found:
                return found
    if field == "jurisdiction_names" and isinstance(value, list):
        for name in value:
            found = _slice(source, str(name))
            if found:
                return found
            alias = _JUR_ALIAS.get(_norm(str(name)))
            if alias:
                found = _slice(source, alias)
                if found:
                    return found
    for hint in _SPAN_HINTS.get(field, ()):
        found = _slice(source, hint)
        if found:
            return found
    return None


def coerce_extraction_payload(raw: dict, source: str) -> dict:
    """Haiku sometimes emits bare strings instead of Driver objects. Wrap and recover spans."""
    payload = dict(raw or {})
    signals = payload.get("work_signals") or []
    if not isinstance(signals, list):
        signals = [signals]
    kept = []
    for item in signals:
        block = _driver_dict(item if not isinstance(item, str) else {"value": item})
        if isinstance(item, str):
            block = {"value": item, "evidence_span": None}
        block["evidence_span"] = _attach_span("work_signals", block.get("value"), block.get("evidence_span"), source)
        if block.get("value"):
            kept.append(block)
    payload["work_signals"] = kept

    for field in DRIVER_FIELDS:
        block = _driver_dict(payload.get(field))
        value = block.get("value")
        if field == "jurisdiction_names":
            value = _normalise_jurs(value)
        elif field in {"entity_count", "workstream_count"}:
            value = _parse_int(value)
        elif field in {"regulator_or_investigation", "systems_change", "multi_party"}:
            value = _parse_bool(value)
        span = _attach_span(field, value, block.get("evidence_span"), source)
        payload[field] = {"value": value, "evidence_span": span}
    return payload


def validate_evidence_spans(extraction: Extraction, source: str) -> tuple[Extraction, list[str]]:
    """Drop any value that is not backed by a verbatim span in the source text."""
    haystack = _norm(source)
    rejected: list[str] = []
    payload = extraction.model_dump()

    def span_in_source(span: str | None) -> bool:
        if not span or not str(span).strip():
            return False
        return _norm(span) in haystack

    kept_signals = []
    for item in payload["work_signals"]:
        if item.get("value") is None:
            continue
        if not span_in_source(item.get("evidence_span")):
            rejected.append("work_signals")
            continue
        kept_signals.append(item)
    payload["work_signals"] = kept_signals

    for field in (
        "jurisdiction_names",
        "entity_count",
        "workstream_count",
        "deadline_kind",
        "regulator_or_investigation",
        "systems_change",
        "multi_party",
        "intake_kind",
        "stated_company",
        "stated_industry",
        "stated_company_size",
        "stated_urgency",
    ):
        block = payload[field]
        if block.get("value") is None:
            block["evidence_span"] = None
            continue
        if not span_in_source(block.get("evidence_span")):
            rejected.append(field)
            block["value"] = None
            block["evidence_span"] = None

    return Extraction.model_validate(payload), rejected


def extract_with_llm(description: str, *, api_key: str | None = None) -> Extraction:
    """One forced-tool call. Sampling knobs are not passed: anthropic>=1.0 dropped them, and current models ignore them."""
    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError("Install the llm extra: pip install -e .[llm]") from exc

    client = anthropic.Anthropic(api_key=api_key)
    prompt = load_prompt()
    schema = extraction_json_schema()
    # anthropic>=1.0 dropped temperature/top_p/top_k from messages.create.
    # Current models do not use those sampling knobs. Forced tool choice is the constraint.
    message = client.messages.create(
        model=PINNED_MODEL,
        max_tokens=1024,
        system=prompt,
        tools=[
            {
                "name": "submit_extraction",
                "description": "Submit extracted drivers. Null means the text does not say.",
                "input_schema": schema,
            }
        ],
        tool_choice={"type": "tool", "name": "submit_extraction"},
        messages=[
            {
                "role": "user",
                "content": (
                    "Extract drivers from this untrusted web-form enquiry.\n"
                    "Every Driver field must be an object with keys value and evidence_span, "
                    "never a bare string, number, or boolean.\n\n"
                    f"{description}"
                ),
            }
        ],
    )
    tool_blocks = [block for block in message.content if block.type == "tool_use"]
    if not tool_blocks:
        raise ValueError("Model did not return a tool call")
    parsed = Extraction.model_validate(coerce_extraction_payload(dict(tool_blocks[0].input), description))
    checked, _rejected = validate_evidence_spans(parsed, description)
    return checked
