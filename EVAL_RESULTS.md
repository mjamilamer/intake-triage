# EVAL_RESULTS

Labels are synthetic and derived from our own scoring function. This measures internal consistency of score/route against locked seeds, not truth. First production deliverable is an adjudicated gold set from real historical enquiries (assumption A13).

## 1. Per-driver extraction accuracy
NOT MEASURED. This run used authored driver vectors, not model output, so the deterministic layer could be tested in isolation. No ANTHROPIC_API_KEY was set when this file was generated, so there is no extraction accuracy number here and I have not estimated one.

What I would run on Monday, in order. First, `extract_with_llm` against all 20 preview descriptions at temperature 0, scoring each of the 9 driver slots three ways: value correct, value correct with a valid evidence span, and span rejected by the substring check. Per-driver accuracy matters more than an aggregate, because a null `entity_count` costs 4 hours of estimate while a wrong `work_signals` costs a misroute to another human. Second, re-run at temperature 0.3 with 3 samples to get a disagreement rate per driver, which is the honest input to the abstention threshold rather than a guessed constant. The current threshold is 1 null scoring driver (A15). Third, feed the extracted vectors, not the authored ones, through score and route to get end-to-end tier and routing accuracy, which is the only number in this document that would mean anything to a partner. That is roughly 80 calls and about an hour of work; the reason it is not here is that the key was absent, not that the plan is unclear.

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
