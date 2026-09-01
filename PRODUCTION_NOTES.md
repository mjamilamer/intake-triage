# PRODUCTION_NOTES

What breaks first is the taxonomy (A3/A15), then out-of-distribution input, then a stale routing table. Not the model weights. Seed 11 exists because two signals can belong to two humans. No model fixes an undefined boundary.

Monitor: reroute-after-assignment by class; abstention trend; class-distribution drift; evidence-span rejection rate; unparseable model outputs; version-pin changes. Baseline these before go-live.

Fallback: abstain with two candidates and hours. Never guess. Kill switch disables the function and returns work to the analyst (slower, not wrong). Round-robin to leads is the degraded auto path if the analyst is out. The analyst becomes the reviewer at residual hours set by the abstention rate, not 8 hours of tagging. Their corrections, written in the empty spreadsheet column, are the signal that improves policy.yaml.

Email / Sheets / JSONL is the working emit path (A7, A8), not a fact from the brief. A different existing stack changes adapters only.
