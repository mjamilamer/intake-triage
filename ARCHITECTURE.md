# ARCHITECTURE

Assumption, not in the brief: the emit path (email, a Google Sheet, a JSONL log) is a working scenario so the prototype has somewhere to write. The brief does not name a stack. If the firm already has a CRM or M365, only the adapters change.

## Data flow

```
web form (Typeform is a fixture; assumption, not in the brief)
  -> normalise to Enquiry
  -> extract.py   one LLM call, forced tool use, facts + verbatim evidence spans
  -> validate     any span not found in the source is rejected and the value nulled
  -> score.py     policy.yaml, no LLM
  -> route.py     policy.yaml, no LLM
  -> email to the lead, or to the analyst on abstain
  -> append spreadsheet row with an empty correction column
  -> append JSONL decision log
```

The boundary is the design. The model returns only observable facts: work signals, jurisdiction names, entity count, workstream count, deadline kind, regulator involvement, systems change, multi-party, and what kind of message this is. It cannot return `service_line`, `complexity`, `estimated_hours`, or `route_to`. Those four are the outputs a partner may have to justify to a client, so they are computed from a file that partner can read.

## Why evidence spans

Every extracted field carries a verbatim quote from the enquiry, and a span that is not a substring of the source is dropped along with its value. This does three things: it turns hallucinated fields into nulls instead of confident errors, it makes the routing email self-explaining ("complex because: two jurisdictions, hard deadline, regulator involved, quoting these phrases"), and it gives an operational metric, span rejection rate, that moves before accuracy visibly degrades.

Null means the text does not say. Null is not zero and not false. A missing entity count is not one entity.

## Untrusted input

The enquiry is a public web form, so the description is hostile by default. Three layers: the prompt states that instruction-like text inside the enquiry is data; the model has no tool that can route or send, so the worst case is a wrong fact rather than a wrong action; and `policy.yaml` carries injection phrases that force an abstention to the analyst. Seed HG-2026-0015 tests exactly this and abstains. Vendor pitches and job applications are classified and abstained as out-of-taxonomy rather than force-fit to a service line.

## Intake schema

Assumption, not in the brief: industry, company size, and urgency are optional picklists. Free text stays. You cannot make a prospect describe their problem in structured form and you would not want to. Better intake makes triage more reliable, but it is not a substitute for the triage system the brief asked for.

## Output surfaces

1. **Structured email to the lead.** Service line, complexity, hours, the rule trace with evidence phrases, the original enquiry underneath. Abstentions go to the analyst with the two candidate lines and both hour estimates, so the human decision is a one-word reply.
2. **Shared spreadsheet as operational ledger.** Append-only, with an empty correction column. That column is the training signal for `policy.yaml`, gathered as a byproduct of work people already do.
3. **Append-only JSONL decision log.** Flat, typed, stable field names. When they buy a CRM they import structured history instead of starting empty.

No UI and no queue app. A four-lead firm cannot maintain one, and the daily surface for a team lead is already their inbox.

Graduation trigger for a real CRM: pipeline visibility, multi-touch attribution, or more than two people editing one record at a time.

## Model and provider

Hosted mid-tier API, temperature 0, forced tool choice, version pinned in `extract.py` (`claude-sonnet-4-6`) and never a latest alias. Routed through whatever cloud they already hold, so this adds no vendor.

What is in the prototype: one Anthropic call at temperature 0, schema generated from the Pydantic model, then span validation. What is not: a provider-swap interface, extra samples at 0.3, or a live extraction eval. Those are the next hour of work if a key is present, not a claim about this repo.

If data residency forbids an external call, the fallback is a local small model. That costs extraction quality and adds hosting. Assumption, not in the brief: Hartwell Grey is ~90 people. Name that trade rather than bury it.

## Day-one instrumentation

Baseline these before deploying anything: submission-to-assignment time, analyst hours, and known misroutes. Without a pre-deploy baseline there is no honest after.

Decision log fields: `enquiry_id`, every driver with its span, `rule_trace`, `route_to`, `abstained` with reason, model and prompt version, sample count, latency, tokens, `decided_at`. Version fields are on every row so a metric shift can be attributed to a prompt change rather than argued about.

Monitoring and failure behaviour: see [PRODUCTION_NOTES.md](PRODUCTION_NOTES.md).

## Deployment posture

Two weeks of shadow mode. Route nothing. Score every live enquiry, let the analyst work normally, and compare. Disagreements get adjudicated. That produces the gold set and the calibrated thresholds at the same time, and it costs the business nothing if the system is wrong.
