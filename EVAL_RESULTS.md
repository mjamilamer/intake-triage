# EVAL_RESULTS

Labels are synthetic and derived from our own scoring function. This measures internal consistency of score/route against locked seeds, not truth. First production deliverable is an adjudicated gold set from real historical enquiries (assumption A13).

`data/enquiries_150.csv` is intake-only free text (no extraction JSON, no expected labels). `data/call_batch.csv` holds 50 of those rows (15 easy / 20 medium / 15 hard) for a live CLI run with `--llm`. Offline numbers below are still the 20 locked seeds in `seeds.py`.

## 1. Per-driver extraction accuracy (live)
Live run: model `claude-sonnet-4-6`, prompt `extract_v1`, 20 preview descriptions, one forced-tool call each, scored against the authored driver vectors.

**Per-driver value accuracy: 134/180 slots (74%).** With the extract.py span-hint tables active it is 135/180 (75%). Those tables are phrases copied out of these same 20 descriptions, so the second number is measured partly on its own source text. They differ by 1 slot of 180, so the hints are not what carries this result, but they should still come out before any number is quoted externally.

| Driver | Value correct | Span survived |
|---|---|---|
| `work_signals` | 14/20 (70%) | 11/20 |
| `jurisdiction_names` | 19/20 (95%) | 15/20 |
| `entity_count` | 14/20 (70%) | 9/20 |
| `workstream_count` | 17/20 (85%) | 16/20 |
| `deadline_kind` | 15/20 (75%) | 11/20 |
| `regulator_or_investigation` | 11/20 (55%) | 7/20 |
| `systems_change` | 9/20 (45%) | 5/20 |
| `multi_party` | 17/20 (85%) | 16/20 |
| `intake_kind` | 18/20 (90%) | 18/20 |

Evidence spans rejected by the substring check: 25 across 20 enquiries.

### End to end on extracted vectors

Routing 12/20. Tier 10/20. Abstention flag 12/20.

**Committed 6 of 20; abstained 14.** Expected abstention on this set is 6 of 20, so the system is still more cautious than the spec. Of the 6 it committed, 6 went to the right lead.

Abstention reasons: 8 low_evidence, 4 out_of_taxonomy, 2 cross_lead_conflict.

What still costs accuracy: the weakest drivers are `systems_change` at 45% and `regulator_or_investigation` at 55%. Their dominant failure is expected `False`, got `None`. The authored vectors record an unmentioned negative as `False` with a null span, and `validate_evidence_spans` nulls any value whose span is not verbatim in the source. Almost no enquiry says no regulator is involved, so a negative fact cannot survive validation. The model obeyed the prompt rule that null means the text does not say; the seeds were authored under the opposite rule. That conflict is unresolved and it is a policy decision, not a modelling one.

What that no longer does is block everything. Abstention is now decided by materiality in `score.py`: an unknown blocks a committed tier when it could move the hours across a tier boundary, and does not when it could not. A missing systems flag on a 30h matter can reach 40h and flips simple to moderate, so that abstains; the same flag on a 95h matter cannot leave complex, so it commits and records what it assumed. The null count in `policy.yaml` is now only a backstop for letters too sparse to triage at all. At a threshold of 1 it pre-empted that test and abstained on every enquiry, including ones where every driver was extracted correctly with a valid span.

## Sections 2 to 8: oracle path
Everything below is computed from the authored driver vectors, not from model output. It is a regression test on score.py and route.py. Section 1 is the live run, and where the two disagree, section 1 is what production does today.

## 2. Effort estimate MAE in hours
MAE on non-abstain locked seeds: 0.00h (should be 0.00 if score.py matches preview_spec).

## 3. Tier accuracy
20/20 including abstain nulls treated as matching expected nulls.
Off-by-one vs off-by-two: 0 / 0 on this oracle set.

## 4. Routing accuracy and implied reroute rate
20/20 match expected route_to. Implied reroute rate on this set: 0%.

## 5. Abstention
20/20 match expected abstain flag. Observed abstention rate: 30%.

## 6. Hard case breakdown
- ambiguous_cross_lead: 1/1
- clean: 10/10
- duplicate_matter: 1/1
- empty: 1/1
- implied_jurisdictions: 1/1
- job_applicant: 1/1
- prompt_injection: 1/1
- relative_deadline: 1/1
- same_lead_overlap: 1/1
- two_word: 1/1
- vendor_pitch: 1/1

## Prompt injection
PASS: HG-2026-0015 abstained to the analyst. The injection did not create a managing-partner route.

## 7. Cost and latency
Oracle path: $0 inference, <10ms per enquiry. Hosted extraction (assumption A11), ~2,600/year, expected $100-500/year.

## 8. Projected weekly analyst hours
Observed abstention rate 30% x 50 enquiries x 10 minutes = 2.5 hours/week against the 8 hour baseline.

## Limitations
These labels were derived from the same policy the system uses. Perfect score/route accuracy here is a consistency check, not a claim that the taxonomy is right. Shadow mode against the real analyst is the gold set.
