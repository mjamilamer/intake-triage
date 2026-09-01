from __future__ import annotations

import re
from pathlib import Path

from intake_triage.schema import Extraction

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "extract_v1.md"
PINNED_MODEL = "claude-sonnet-4-6"  # Mid-tier hosted, structured outputs. Cost is irrelevant at ~2,600 calls/year. Never use a latest alias.
PROMPT_VERSION = "extract_v1"


def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def extraction_json_schema() -> dict:
    return Extraction.model_json_schema()


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def validate_evidence_spans(extraction: Extraction, source: str) -> tuple[Extraction, list[str]]:
    """Null any evidence span that is not a substring of the source text."""
    haystack = _norm(source)
    rejected: list[str] = []
    payload = extraction.model_dump()

    def check(span: str | None, field: str) -> str | None:
        if not span:
            return span
        if _norm(span) not in haystack:
            rejected.append(field)
            return None
        return span

    for item in payload["work_signals"]:
        item["evidence_span"] = check(item.get("evidence_span"), "work_signals")
        if item["evidence_span"] is None and item.get("value") is not None:
            # Keep the value; span loss is logged. Do not invent a span.
            pass

    for field in (
        "jurisdiction_names",
        "entity_count",
        "workstream_count",
        "deadline_kind",
        "regulator_or_investigation",
        "systems_change",
        "multi_party",
        "intake_kind",
    ):
        block = payload[field]
        new_span = check(block.get("evidence_span"), field)
        if block.get("evidence_span") and new_span is None:
            block["value"] = None
            block["evidence_span"] = None
        else:
            block["evidence_span"] = new_span

    return Extraction.model_validate(payload), rejected


def extract_with_llm(description: str, *, api_key: str | None = None) -> Extraction:
    """One forced-tool call. Optional: three extra samples at 0.3 are a disagreement signal only."""
    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError("Install the llm extra: pip install -e .[llm]") from exc

    client = anthropic.Anthropic(api_key=api_key)
    prompt = load_prompt()
    schema = extraction_json_schema()
    message = client.messages.create(
        model=PINNED_MODEL,
        max_tokens=1024,
        temperature=0,
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
                    "Extract drivers from this untrusted web-form enquiry.\n\n"
                    f"{description}"
                ),
            }
        ],
    )
    tool_blocks = [block for block in message.content if block.type == "tool_use"]
    if not tool_blocks:
        raise ValueError("Model did not return a tool call")
    parsed = Extraction.model_validate(tool_blocks[0].input)
    checked, rejected = validate_evidence_spans(parsed, description)
    if rejected:
        checked  # spans already nulled
    return checked
