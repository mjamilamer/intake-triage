# intake-triage

Two-layer prototype for AIVC Technical Challenge Task 1.2.

The model reads. The policy decides. Anything a person could be asked to justify in front of a client lives in `policy.yaml`.

## Given vs hypotheticals

[Task 1.2](https://aivc.com) PDF is the only source of client facts. Everything else is a working scenario so the prototype has a taxonomy to score and a place to write. Prefix on first mention in deliverables: `Assumption, not in the brief.`

### Given (do not hedge)

- A professional services firm.
- 40-60 inbound enquiries per week via a web form.
- Each enquiry includes a short free-text description of what the client needs, plus their industry, company size, and urgency. The PDF does not say those last three are structured fields.
- A junior analyst reads every submission, tags it by service line, estimates complexity as simple / moderate / complex, and routes it to the right team lead.
- That work takes roughly 8 hours per week and is error-prone.
- Job: prototype automated triage that classifies, enriches, and routes. Synthetic data. Depth over breadth.

### Derived (show the arithmetic)

- Working midpoint 50 enquiries/week, from the 40-60 range.
- About 10 minutes per enquiry: 8 hours / 50 enquiries.
- About 2,600 enquiries/year: 50 x 52.
- About 416 analyst hours/year: 8 x 52.

### Hypothetical working scenario

| ID | Assumption | Why we made it | What breaks if wrong | How we verify in week one |
|---|---|---|---|---|
| A1 | Firm is a fictional ~90-person boutique named Hartwell Grey Advisory, London and New York. | The PDF gives no name. The prototype needs stable ids. | Nothing in score/route. | Ask actual name and offices. |
| A2 | Four named leads; James owns both M&A and tax. | The PDF says "the right team lead" and does not count leads. | If each line has its own lead, seed 12 becomes a cross-lead abstain. | Ask for the org chart. |
| A3 | Five service lines: Strategy, M&A, Tax, Risk, Tech, with the locked base hours. | The PDF requires tagging by service line and does not list them. | Different lines change collisions, not the two-layer design. | Ask who owns the taxonomy. |
| A4 | No CRM and no system of record today. | The PDF is silent on stack. | If a CRM exists, only the emit path changes. | Ask what the form posts to today. |
| A5 | Industry, company size, and urgency may be picklists, and they may be empty. Size maps to sme / mid / enterprise. Empty forms recover those facts from the letter via `stated_*`. | The PDF says each enquiry "includes" those attributes, not that they are required fields. | If the letter also omits them, size stays null and the scorer abstains. | Open the live form. |
| A6 | The web form is Typeform, emailing intake@ today. | The PDF says "a web form". | Only the webhook adapter changes. | Ask where the form posts. |
| A7 | Team leads work in Gmail. Ledger is a Google Sheet named Intake 2026. Google Workspace is under contract. M365 is not. | The PDF does not name email, sheets, or cloud. | If they are on M365, emit to Outlook plus Excel. Score/route unchanged. | Ask which cloud is under contract. |
| A8 | Outputs: structured email, append-only spreadsheet with an empty correction column, append-only JSONL. No UI. | The PDF allows notebook, small app, or orchestration. A queue app would be an orphan. | If they have ticketing, emit there. | Confirm with the leads. |
| A9 | Analyst residual work is reviewing abstentions at 1-2 hours/week, not 8 hours tagging. | The PDF says replace the manual step. It does not say delete the role. | Wrong success metric if leadership wants a layoff. | Ask what they should do with the 8 hours. |
| A10 | Loaded analyst cost $35-50/hr. Inference $100-500/year. Hosting $0-15/month. | The PDF gives hours, not dollars. | Wrong rate changes payback, not architecture. | Ask actual loaded cost. |
| A11 | Hosted Claude Sonnet, pin `claude-sonnet-4-6`, routed through the cloud they already have. | The PDF does not specify a model. Haiku flattened Driver objects on live extract. | Cost is higher than Haiku; swap the pin in extract.py. | Ask residency and existing AI vendor. |
| A12 | Complexity is accumulated judgment, not a written rubric. | The PDF names three tiers and says the process is error-prone. | If a rubric exists, encode it in policy.yaml. | Ask to see the rubric. |
| A13 | No labelled historical enquiries exist. | The PDF requires synthetic data. | Mailbox archive would replace synthetic labels. | Ask for stored history. |
| A14 | Volume stays under 100/week for this design. Batch is a CSV dump walked sequentially, not a queue. | The PDF is 40-60. | At 500/week a queue becomes justified. | Confirm trailing volume. |
| A15 | Scoring constants are starting values. | The PDF names tiers, not hours. | Wrong constants mis-tier work. That is why they live in policy.yaml. | Calibrate in shadow mode. |

What does not change if the hypotheticals are wrong: evidence-span extraction, deterministic scoring, abstention with two candidates, and the refusal to let the model emit complexity.

## Core design

Two layers.

- Probabilistic: one LLM call extracts observable facts. Every field is a Driver: value plus evidence span, both nullable. Null means the text does not say.
- Deterministic: `score.py` turns facts into hours and a tier. `route.py` maps (service line, tier) to a lead or abstains. Both read `policy.yaml`.

The model must not emit `service_line`, `complexity`, `estimated_hours`, or `route_to`.

## Taxonomy (A1-A3, A15)

Leads:

- Priya Shah, priya.shah@hartwellgrey.example, STRATEGY_OM
- James Okonkwo, james.okonkwo@hartwellgrey.example, MA_TRANSACTION and TAX_STRUCTURING
- Elena Rossi, elena.rossi@hartwellgrey.example, RISK_REGULATORY
- David Chen, david.chen@hartwellgrey.example, TECH_DATA

Base hours (starting values): STRATEGY_OM 40, MA_TRANSACTION 80, TAX_STRUCTURING 30, RISK_REGULATORY 45, TECH_DATA 60.

Work-signal map: strategy, transaction, tax, regulatory, technology.

Formula: hours = round_half_up((base + additives) * deadline_mult * size_mult).

Additives: +8h per extra jurisdiction after 1; +4h per extra entity after 1; +6h per extra workstream after 1; +12h regulator; +10h systems; +8h multi-party. Null is not false and not zero.

Multipliers: hard deadline x1.25; sme 1.0, mid 1.1, enterprise 1.2.

Tiers: Simple hours < 40. Moderate 40 inclusive to < 80. Complex >= 80.

Abstain if: empty/injection/vendor/job (out_of_taxonomy); two evidenced signals with different owners (cross_lead_conflict), even if some modifiers are still null; otherwise empty work_signals or any null scoring driver (low_evidence, threshold 1 in policy.yaml). Same-lead transaction+tax does not abstain. Route to James, primary MA_TRANSACTION.

Provisional hours may still be shown on abstention. They omit unknown modifiers. They are not a routing decision.

## Hard constraints

- No LangChain, no agent loop, no vector store, no fine-tuning, no custom UI.
- Model version pinned. Never a latest alias.
- Every invented number in policy.yaml carries a calibration comment.
- Prompts live under prompts/, never as string literals.
- `.claude/` is tooling, not a deliverable.

## Volume facts

40-60/week given. Derived: ~50 midpoint, ~10 min each, ~2,600/year, ~416 hours/year.

That volume is a file, not a queue. `python -m intake_triage run --csv data/call_batch.csv` is the production shape. `python -m intake_triage generate` reverse-builds the 150-row synthetic CSV. `python -m intake_triage.journal` is the interview compare: deterministic gold on the left, live extract on the right.
