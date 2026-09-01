# intake-triage

## What I built

Two-layer triage for a professional-services inbound form. One extraction call reads free text into evidenced facts. `policy.yaml` scores hours, assigns simple/moderate/complex, and routes to a team lead or abstains. The model reads. The policy decides.

The model cannot emit `service_line`, `complexity`, `estimated_hours`, or `route_to`. Those are the four outputs someone has to defend to a client, so they come from a file a partner can read.

## What I deliberately did not build

- Agent loop: one extraction call is the entire probabilistic step.
- Vector store: there is no corpus to retrieve from.
- Fine-tuning: ~2,600 examples/year against a taxonomy that will change, and it would destroy evidence-span behaviour.
- Orchestration framework: one deterministic path.
- Custom UI as a product: a four-lead firm will not maintain one. The journal at `python -m intake_triage.journal` is an interview walkthrough only. Production is `python -m intake_triage run` against a form dump.

## Working scenario

Assumption, not in the brief: Hartwell Grey, the five-line taxonomy, Typeform, and the Google Sheet are fixtures so the prototype has a taxonomy to score and somewhere to write. The brief names a web form, a short free-text description, industry, company size, urgency, and "the right team lead". It names no firm, no stack, and no service lines. If the real firm runs Salesforce or M365, only the emit adapters change. Score and route do not.

## Volume

Given: 40-60 enquiries/week. Derived: midpoint (40+60)/2 = 50/week; 8 hours / 50 = 0.16h = ~10 minutes per enquiry; 50 x 52 = ~2,600/year; 8 x 52 = 416 analyst hours/year. That volume is a CSV dump walked sequentially, not a queue.

## Results

See [EVAL_RESULTS.md](EVAL_RESULTS.md). Score and route match the locked spec at 0h MAE. That is internal consistency against labels derived from the same policy, not extraction accuracy and not truth. Prompt injection seed HG-2026-0015 abstains to the analyst rather than routing to a managing partner. Abstention on this set is 30% because the 20 seeds are deliberately weighted to hard cases, not because 30% of live traffic would abstain.

## How to run

Install once:

```
python -m pip install -e ".[dev,ui]"
python -m pytest
```

### Journal (interview walkthrough, not production)

```
python -m intake_triage.journal
```

Open `http://127.0.0.1:8765`. Put `ANTHROPIC_API_KEY` in `.env` at the repo root, then start the process. The page is a teaching surface: one enquiry at a time so a panel can see the two layers. Production is still the CLI against a CSV dump.

Every pack uses the same compare layout.

- **Left, Deterministic:** authored or reverse-generated drivers through `score.py` / `route.py`. No LLM.
- **Right, Live LLM:** one pinned extract, then the same scorer and router.
- Email under each column. Form picklists win when present. If they are empty, company, industry, size, urgency, and a short brief come from the letter (`stated_*`), labelled `(from letter)`.

Packs:

- **Interview:** panel fixtures, hard and very-hard letters, two form-empty letters (Whitcombe `0213`, Harbor & Pine `0214`).
- **Test:** interview plus long letters and the remaining form-empty cases.
- **Browse:** Call 50 or All 150. Journal-only extras are not in those CSVs.

Buttons: **Compare new** / **Rerun compare**. Restart the journal after Python changes (`reload=False`). Refresh the page after HTML changes.

### Without LLM (locked seeds only)

The 20 fixtures live in `intake_triage/seeds.py`. Offline runs use those authored drivers. The CSVs do not contain extraction JSON.

```
python -m intake_triage run --id HG-2026-0011
python -m intake_triage run --id HG-2026-0012
python -m intake_triage run --id HG-2026-0015
```

`0001` easy tax, `0011` cross-lead hold, `0012` M&A+tax to James, `0015` injection hold.

### With LLM (production path)

CSVs and pasted text are intake only. `--llm` is what reads the free text.

```
python -m pip install -e ".[llm]"
```

Windows PowerShell:

```
$env:ANTHROPIC_API_KEY = "..."
```

Smoke one locked seed (compare live extract to the authored path):

```
python -m intake_triage run --id HG-2026-0011 --llm
```

One generated example from the 150:

```
python -m intake_triage run --id HG-2026-0127 --llm
```

Paste live prose:

```
python -m intake_triage run --text "Need a UK corporation-tax issue reviewed. One UK company only." --company "Northbridge Payroll Ltd" --industry professional_services --llm
```

In the journal, **Compare new** runs both columns. Model version is pinned in `extract.py` as `claude-sonnet-4-6`, never a latest alias.

### Batch (morning spreadsheet dump)

50 held-out rows in `data/call_batch.csv` (15 easy / 20 medium / 15 hard). First six rows are the panel set.

Without `--llm`, locked ids in that file still score from `seeds.py`; generated ids abstain. Use `--llm` to test extraction on the form dump.

```
python -m intake_triage run --csv data/call_batch.csv --llm --limit 3
python -m intake_triage run --csv data/call_batch.csv --difficulty hard --llm
python -m intake_triage run --csv data/call_batch.csv --llm
```

Full 150: `--csv data/enquiries_150.csv`. Decisions land under `data/out/`.

### Generate the 150 intake examples

```
python -m intake_triage generate --explain
python -m intake_triage generate
```

Method: sample drivers, score and route by construction, write free text that contains those spans. The CSV keeps only what a web form would send. Labels are not written into the file.

## Repo layout

- `policy.yaml`, `intake_triage/score.py`, `intake_triage/route.py`: deterministic core
- `intake_triage/extract.py`, `prompts/extract_v1.md`: the only production LLM path
- `intake_triage/emit.py`: lead email and spreadsheet row. Letter-backed fields when the form is empty.
- `intake_triage/seeds.py`, `data/preview.jsonl`: 20 reverse-specified synthetics
- `intake_triage/journal_extras.py`: interview-only hard, long, and form-empty letters. Not in the CSVs.
- `intake_triage/synth.py`, `data/enquiries_150.csv`: 150 intake-only free-text rows (20 locked seeds plus 130 generated). No extraction JSON.
- `data/call_batch.csv`: 50 held-out rows, 15 easy / 20 medium / 15 hard, for a live run
- `data/corpus.csv`: the other 100
- `python -m intake_triage run`: one id, pasted text, or a CSV batch. Add `--llm` to extract from the description.
- `python -m intake_triage.journal`: interview compare UI
- `demo.ipynb`: walkthrough, no scoring logic
- Docs: [CLARIFYING_QUESTIONS.md](CLARIFYING_QUESTIONS.md), [ARCHITECTURE.md](ARCHITECTURE.md), [BUSINESS_CASE.md](BUSINESS_CASE.md), [PRODUCTION_NOTES.md](PRODUCTION_NOTES.md), [PANEL_DRILL.md](PANEL_DRILL.md), [AGENTS.md](AGENTS.md)

Scoring and routing live in modules, not the notebook, so they can be unit tested.

## The unresolved question

Seed 11 (strategy plus regulatory) abstains because the two signals have different owners. Seed 12 (transaction plus tax) does not, because one lead owns both. That is a policy choice written in a file, not a model behaviour. Those pairs collide because the taxonomy has undefined boundaries, and no model fixes an undefined boundary. Week one is sitting with the leads until they can say out loud which collisions they want routed and which they want sent back.
