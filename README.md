# intake-triage

## What I built

Two-layer triage for a professional-services inbound form. One extraction call reads free text into evidenced facts. `policy.yaml` scores hours, assigns simple/moderate/complex, and routes to a team lead or abstains. The model reads. The policy decides.

The model cannot emit `service_line`, `complexity`, `estimated_hours`, or `route_to`. Those are the four outputs someone has to defend to a client, so they come from a file a partner can read.

## What I deliberately did not build

- Agent loop: one extraction call is the entire probabilistic step.
- Vector store: there is no corpus to retrieve from.
- Fine-tuning: ~2,600 examples/year against a taxonomy that will change, and it would destroy evidence-span behaviour.
- Orchestration framework: one deterministic path.
- Custom UI as a product: a four-lead firm will not maintain one. The journal at `python -m intake_triage.journal` is an interview walkthrough only.

## Working scenario

Assumption, not in the brief: Hartwell Grey, the five-line taxonomy, Typeform, and the Google Sheet are fixtures so the prototype has a taxonomy to score and somewhere to write. The brief names a web form, a short free-text description, industry, company size, urgency, and "the right team lead". It names no firm, no stack, and no service lines. If the real firm runs Salesforce or M365, only the emit adapters change. Score and route do not.

## Volume

Given: 40-60 enquiries/week. Derived: midpoint (40+60)/2 = 50/week; 8 hours / 50 = 0.16h = ~10 minutes per enquiry; 50 x 52 = ~2,600/year; 8 x 52 = 416 analyst hours/year.

## Results

See [EVAL_RESULTS.md](EVAL_RESULTS.md). Score and route match the locked spec at 0h MAE. That is internal consistency against labels derived from the same policy, not extraction accuracy and not truth. Prompt injection seed HG-2026-0015 abstains to the analyst rather than routing to a managing partner. Abstention on this set is 30% because the 20 seeds are deliberately weighted to hard cases, not because 30% of live traffic would abstain.

## How to run

```
python -m pip install -e ".[dev,ui]"
python -m pytest
python -m intake_triage.evaluate
python -m intake_triage.journal
```

Open `http://127.0.0.1:8765`. The journal is an interview walkthrough, not the production surface.

Optional live LLM in the journal: `pip install -e ".[llm]"`, set `ANTHROPIC_API_KEY`, then tick "Live LLM". Model version is pinned in `extract.py`, never a latest alias.

## Repo layout

- `policy.yaml`, `intake_triage/score.py`, `intake_triage/route.py`: deterministic core
- `intake_triage/extract.py`, `prompts/extract_v1.md`: the only production LLM path
- `intake_triage/seeds.py`, `data/preview.jsonl`: 20 reverse-specified synthetics
- `demo.ipynb`: walkthrough, no scoring logic
- Docs: [CLARIFYING_QUESTIONS.md](CLARIFYING_QUESTIONS.md), [ARCHITECTURE.md](ARCHITECTURE.md), [BUSINESS_CASE.md](BUSINESS_CASE.md), [PRODUCTION_NOTES.md](PRODUCTION_NOTES.md), [PANEL_DRILL.md](PANEL_DRILL.md), [AGENTS.md](AGENTS.md)

Scoring and routing live in modules, not the notebook, so they can be unit tested.

## The unresolved question

Seed 11 (strategy plus regulatory) abstains because the two signals have different owners. Seed 12 (transaction plus tax) does not, because one lead owns both. That is a policy choice written in a file, not a model behaviour. Those pairs collide because the taxonomy has undefined boundaries, and no model fixes an undefined boundary. Week one is sitting with the leads until they can say out loud which collisions they want routed and which they want sent back.
