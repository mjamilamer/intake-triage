# PRODUCTION_NOTES

**What breaks first is the taxonomy, not the model.** Then out-of-distribution input, then a stale routing table when someone changes role. Model weights are pinned and will not drift; the org chart will. Seed 11 exists because two work signals can belong to two humans, and no model resolves an undefined boundary.

**Monitor, baselined before go-live:** reroute-after-assignment by class (the free and truest error signal), abstention rate trend, class-distribution drift, evidence-span rejection rate, unparseable model outputs, and every version-pin change. Span rejection and abstention move before accuracy visibly degrades, which is why they are the alarms rather than the report.

**Fallback is always abstain, never guess.** An abstention routes to the analyst with the two candidate lines and both hour estimates, so a human decision costs one word. A model outage or an unparseable row is labelled `extraction_failed`, not `low_evidence`, and writes a copy under `data/out/review/`. The kill switch disables the function entirely and returns work to the analyst: slower, not wrong. If the analyst is out, degraded auto-routing is round-robin across leads, which is what happens today anyway.

**Batch is a file, not a job queue.** Forty to sixty rows a week is a CSV export from the form, walked sequentially. `intake_triage.batch` isolates failures: a poisoned description or a missing extraction is one HOLD row, not a stalled morning. Retry is rerun-the-id (`python -m intake_triage run --id HG-2026-0011`), not replay-the-topic. Parallel workers are a later conversation at roughly 500/week.

**The analyst becomes the reviewer,** at residual hours set by the abstention rate rather than 8 hours of tagging. Their corrections, written into the empty spreadsheet column, are the only signal that improves `policy.yaml`. If nobody fills that column, the system stops learning and we should know that within a fortnight.

**Empty form fields do not blank the lead email.** `emit.py` uses form picklists when they are present. When they are not, it copies `stated_*` from the letter and labels them `(from letter)`, plus a two-sentence brief. The scorer already uses letter size the same way. Guessing a missing size is still forbidden.

Assumption, not in the brief: the email, Sheets, and JSONL emit path. A different existing stack changes adapters only.
