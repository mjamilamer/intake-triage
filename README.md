# intake-triage

## What I built

Two-layer triage for a professional-services inbound form. One extraction step reads free text into evidenced facts. `policy.yaml` scores hours, assigns simple/moderate/complex, and routes to a team lead or abstains. The model reads. The policy decides.

## What I deliberately did not build, and why

- Agent loop: one extraction call is the probabilistic step.
- Vector store: there is no corpus.
- Fine-tuning: ~2,600 examples/year and a changing taxonomy.
- Orchestration framework: one deterministic path.
- Custom UI: a four-lead firm cannot maintain it. It would become an orphan.

## Working scenario (not in the brief)

Hartwell Grey, Typeform, Gmail, and Google Sheets are assumptions A1/A6/A7. They are fixtures so the prototype can emit somewhere. The brief names a web form, not a stack. If the real firm has Salesforce or M365, only adapters change.

## Headline numbers (oracle run on 20 locked seeds)

See [EVAL_RESULTS.md](EVAL_RESULTS.md). Score/route match the locked spec (MAE 0h). That is internal consistency, not truth. Prompt injection (HG-2026-0015) abstains to the analyst and does not create a managing-partner route. Observed abstention on this set is high because the 20 seeds are biased toward hard cases, not the live mix.

## How to run

```
python -m pip install -e ".[dev]"
python -m pytest
python -m intake_triage.evaluate
```

Optional LLM extraction: `pip install -e ".[llm]"` and call `extract_with_llm` with `ANTHROPIC_API_KEY`. Pinned model is `claude-sonnet-4-6`.

## Repo layout

- `policy.yaml` / `intake_triage/score.py` / `intake_triage/route.py`: deterministic core
- `intake_triage/extract.py` / `prompts/extract_v1.md`: the only production LLM path
- `intake_triage/seeds.py` / `data/preview.jsonl`: 20 reverse-specified synthetics
- `demo.ipynb`: walkthrough, no scoring logic
- Documents: [CLARIFYING_QUESTIONS.md](CLARIFYING_QUESTIONS.md), [ARCHITECTURE.md](ARCHITECTURE.md), [BUSINESS_CASE.md](BUSINESS_CASE.md), [PRODUCTION_NOTES.md](PRODUCTION_NOTES.md), [AGENTS.md](AGENTS.md)

Logic lives in modules so scoring and routing can be unit tested. That is hard in a notebook.

## Unresolved policy questions

Seed 11 (strategy + regulatory) abstains because owners differ. Seed 12 (transaction + tax) does not, because James owns both. That is a policy choice, not a model choice. Those pairs collide because the taxonomy has undefined boundaries. No model fixes that. Week one is sitting with the leads until they can say, out loud, which collisions they want routed and which they want sent back.
