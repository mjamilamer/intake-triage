# EVAL_RESULTS

Labels are synthetic and derived from our own scoring function. This measures internal consistency of score/route against locked seeds, not truth. First production deliverable is an adjudicated gold set from real historical enquiries (assumption A13).

## 1. Per-driver extraction accuracy
Not measured in this run. The 20 preview records use authored driver vectors so we can test the deterministic layer in isolation. Wire extract.py to a pinned model to fill this block.

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
