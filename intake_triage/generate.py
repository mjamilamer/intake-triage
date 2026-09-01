from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from intake_triage.schema import Enquiry, Extraction
from intake_triage.seeds import SEEDS

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def seed_to_enquiry(seed: dict) -> Enquiry:
    return Enquiry(
        enquiry_id=seed["enquiry_id"],
        submitted_at=datetime.fromisoformat(seed["submitted_at"].replace("Z", "+00:00")),
        contact_name=seed.get("contact_name"),
        contact_email=seed.get("contact_email"),
        company_name=seed["company_name"],
        industry=seed["industry"],
        company_size=seed["company_size"],
        urgency=seed["urgency"],
        description=seed["description"],
    )


def seed_to_extraction(seed: dict) -> Extraction:
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
