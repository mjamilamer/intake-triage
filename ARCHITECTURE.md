# ARCHITECTURE

The brief does not specify the current stack. Email plus a Google Sheet plus JSONL is a working scenario (A7, A8) so the prototype has somewhere to write. If they already have a CRM or M365, only the emit adapters change. Score and route do not.

## Data flow

```
web form (A6 Typeform is a fixture)
  -> normalise Enquiry
  -> extract.py  (one LLM call, facts + evidence spans)
  -> score.py    (policy.yaml, no LLM)
  -> route.py    (policy.yaml, no LLM)
  -> email to lead, or analyst if abstain
  -> append spreadsheet row (empty correction column)
  -> append JSONL decision log
```

The model reads. The policy decides. The model does not emit service_line, complexity, hours, or route_to.

## Intake schema

The PDF says each enquiry includes industry, company size, and urgency. Treating those as optional picklists is assumption A5. Free text stays. You cannot make a prospect describe their problem in structured form, and you would not want to. Every added required field costs conversions. Fixing intake makes triage more reliable. It is not a replacement for the triage system the brief asked for.

## Output surfaces (greenfield, A4/A8)

1. Structured email to the team lead: service line, complexity, hours, rule trace with evidence phrases, original enquiry below. Abstentions go to the analyst with two candidates. A one-word reply captures the correction.
2. Shared spreadsheet as the operational ledger, append-only, empty correction column. Assumption A7 names it Intake 2026 on Google Sheets. That name is a fixture.
3. Append-only JSONL decision log. Flat, typed, stable field names. When they buy a CRM they import structured history instead of starting empty.

I did not build a UI or a queue app. A four-lead firm cannot maintain one. It would become an orphan. Building it would contradict the argument this document is making.

Graduation trigger for a CRM: pipeline visibility, multi-touch attribution, or more than two people editing the same record concurrently.

## Model and provider

Hosted API, mid-tier, forced tool choice, pinned version (`claude-sonnet-4-6` in extract.py). Routed through their existing cloud so this adds no vendor (A11). Thin provider interface so Azure OpenAI or Vertex is a config change. Local small-model fallback if residency forbids external calls: lower extraction quality plus hosting nobody there can maintain. Name that cost rather than bury it.

## What I did not build

- Agent loop: one extraction call is the probabilistic step.
- Vector store: there is no corpus.
- Fine-tuning: ~2,600 examples/year, changing taxonomy, and it would destroy evidence-span behaviour.
- Orchestration framework: one deterministic path.
- Custom UI: see A8.

## Day-one instrumentation

Baseline before deploy: time from submission to assignment, analyst hours, known misroutes.

Decision log fields: enquiry_id, drivers plus spans, rule_trace, route, abstained, model/prompt versions, samples, latency, tokens, decided_at.

Business metrics: reroute-after-assignment by class (free and truest error signal), submission-to-assignment time, analyst hours reclaimed, escalation volume trend, evidence-span rejection rate, unparseable outputs, version-pin changes.

## Deployment posture

Two weeks shadow mode. Route nothing. Measure agreement. Adjudicate disagreements. That produces the gold set and the thresholds at once and costs the business nothing.
