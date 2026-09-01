"""CLI for one enquiry, a CSV dump, or reverse-generated synthetic rows.

Production shape: `python -m intake_triage run --csv data/call_batch.csv --llm`
Interview: `python -m intake_triage.journal`
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from intake_triage.batch import (
    format_single,
    load_csv,
    lookup_record,
    process_batch,
    process_row,
)
from intake_triage.generate import DATA_DIR


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m intake_triage",
        description="Run one enquiry or a CSV batch. Generate synthetic free-text examples.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="Score/route one id, pasted text, or a CSV batch")
    run.add_argument("--id", help="Enquiry id, e.g. HG-2026-0011")
    run.add_argument("--csv", type=Path, help="Batch CSV (default data/call_batch.csv if neither --id nor --text)")
    run.add_argument("--from-csv", type=Path, dest="from_csv", help="CSV used to resolve --id")
    run.add_argument("--difficulty", choices=["easy", "medium", "hard"], help="Filter a batch")
    run.add_argument("--text", help="Raw free-text description for a one-off")
    run.add_argument("--company", default="Walk-in Ltd")
    run.add_argument("--industry", default="other")
    run.add_argument("--size", default="sme", dest="company_size")
    run.add_argument("--urgency", default="normal")
    run.add_argument("--llm", action="store_true", help="Call extract.py (needs ANTHROPIC_API_KEY)")
    run.add_argument("--limit", type=int, help="Process only the first N matching rows of a batch")
    run.add_argument("--json", action="store_true", dest="as_json", help="Print the full decision JSON")
    run.add_argument("--out", type=Path, default=DATA_DIR / "out", help="Batch output directory")

    gen = sub.add_parser("generate", help="Reverse-generate synthetic CSV examples")
    gen.add_argument("--n", type=int, default=150)
    gen.add_argument("--call-n", type=int, default=50)
    gen.add_argument("--explain", action="store_true", help="Print how generation works and exit")

    return parser


def _explain() -> str:
    return """
CSVs are form dumps: free text plus industry, size, urgency. No extraction JSON.

Without LLM (locked seeds HG-2026-0001..0020, authored drivers in seeds.py)
  python -m intake_triage run --id HG-2026-0011
  python -m intake_triage run --id HG-2026-0012
  python -m intake_triage run --id HG-2026-0015

With LLM (extracts from the description; this is the production path)
  pip install -e ".[llm]"
  set ANTHROPIC_API_KEY=...
  python -m intake_triage run --id HG-2026-0011 --llm
  python -m intake_triage run --id HG-2026-0127 --llm
  python -m intake_triage run --csv data/call_batch.csv --llm --limit 3
  python -m intake_triage run --csv data/call_batch.csv --difficulty hard --llm
  python -m intake_triage run --text "Need a UK corporation-tax issue reviewed. One UK company." --company "Northbridge Payroll Ltd" --industry professional_services --llm

Journal
  python -m intake_triage.journal
  Open http://127.0.0.1:8765
  Left column is deterministic gold. Right column is the live extract.

Generate intake CSVs
  python -m intake_triage generate
""".strip()


def _one_off_text(args) -> dict:
    from datetime import datetime, timezone

    row = {
        "enquiry_id": "HG-LIVE-0001",
        "submitted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "contact_name": "",
        "contact_email": "",
        "company_name": args.company,
        "industry": args.industry,
        "company_size": args.company_size,
        "urgency": args.urgency,
        "description": args.text,
        "difficulty": "",
        "split": "live",
        "hard_case_type": "",
    }
    return process_row(row, use_llm=args.llm)


def main(argv: list[str] | None = None) -> int:
    """Dispatch run / generate. Returns a process exit code."""
    args = _parser().parse_args(argv)
    if args.cmd == "generate":
        if args.explain:
            print(_explain())
            return 0
        from intake_triage.synth import generate_and_write

        paths = generate_and_write(args.n, args.call_n)
        print("Wrote intake-only CSVs (no extraction JSON)")
        for key, path in paths.items():
            print(f"  {key}: {path}")
        return 0

    if args.text:
        result = _one_off_text(args)
        print(json.dumps(result["output_json"], indent=2) if args.as_json else format_single(result))
        return 0

    if args.id:
        rows = load_csv(args.from_csv) if args.from_csv else None
        if rows is None and (DATA_DIR / "enquiries_150.csv").exists() and not args.csv:
            try:
                rows = load_csv(DATA_DIR / "enquiries_150.csv")
            except OSError:
                rows = None
        try:
            row = lookup_record(args.id, rows)
        except KeyError as exc:
            print(str(exc))
            return 1
        result = process_row(row, use_llm=args.llm)
        print(json.dumps(result["output_json"], indent=2) if args.as_json else format_single(result))
        return 0

    csv_path = args.csv or (DATA_DIR / "call_batch.csv")
    if not csv_path.exists():
        print(f"No CSV at {csv_path}. Generate first: python -m intake_triage generate")
        return 1
    rows = load_csv(csv_path)
    result = process_batch(
        rows,
        use_llm=args.llm,
        difficulty=args.difficulty,
        limit=args.limit,
        out_dir=args.out,
    )
    summary = result["summary"]
    print(json.dumps(summary, indent=2))
    print()
    for item in result["results"]:
        d = item["decision"]
        flag = "HOLD" if d["abstained"] else (d["complexity"] or "").upper()
        src = item["extraction_source"]
        print(f"{item['enquiry_id']:16} {item['difficulty']:7} {flag:8} {src:18} {d['route_to']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
