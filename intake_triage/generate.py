"""Turn a seed dict into Enquiry / Extraction. Also writes data/preview.jsonl."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from intake_triage.schema import Enquiry, Extraction
from intake_triage.seeds import SEEDS

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _blank(value):
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value


def seed_to_enquiry(seed: dict) -> Enquiry:
    """Build an Enquiry. Blank company/industry/size/urgency become null."""
    return Enquiry(
        enquiry_id=seed["enquiry_id"],
        submitted_at=datetime.fromisoformat(seed["submitted_at"].replace("Z", "+00:00")),
        contact_name=_blank(seed.get("contact_name")),
        contact_email=_blank(seed.get("contact_email")),
        company_name=_blank(seed.get("company_name")),
        industry=_blank(seed.get("industry")),
        company_size=_blank(seed.get("company_size")),
        urgency=_blank(seed.get("urgency")),
        description=seed["description"],
    )


def seed_to_extraction(seed: dict) -> Extraction:
    """Authored gold drivers. Used offline. Live extract never copies this JSON."""
    return Extraction.model_validate(seed["extraction"])


def write_preview(path: Path | None = None) -> Path:
    """Reverse generation for the locked 20: driver vector is authored first, prose is fixtures."""
    target = path or (DATA_DIR / "preview.jsonl")
    spec_path = DATA_DIR / "preview_spec.json"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(json.dumps(SEEDS, indent=2), encoding="utf-8")
    with target.open("w", encoding="utf-8") as handle:
        for seed in SEEDS:
            handle.write(json.dumps(seed) + "\n")
    return target


if __name__ == "__main__":
    out = write_preview()
    print(f"Wrote {len(SEEDS)} records to {out}")
