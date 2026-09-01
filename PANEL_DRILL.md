# PANEL_DRILL

Ten questions a technical panel is most likely to ask, hardest first. Each answer is two sentences, meant to be said out loud. Questions marked **WEAKNESS** are ones where the honest answer is that the work is incomplete. Say the weakness first and do not decorate it.

---

### 1. Your eval labels come from the same policy the system uses. What does 0h MAE actually prove? **WEAKNESS**

It proves internal consistency and nothing else: I wrote the expected hours by hand from the spec, and `score.py` reproduces them, so this is a regression test that would catch me breaking the scorer, not evidence the tiers are right. The real measurement is two weeks of shadow mode where the analyst tags normally and we adjudicate every disagreement, and until that happens I have no accuracy number worth quoting.

### 2. You ran the model. What happened? **WEAKNESS**

Per-driver value accuracy is 74% of 180 slots, and end to end it commits on 6 of 20 and abstains on 14, with all 6 of the commitments going to the right lead. High precision and low recall is the right way round for triage, but 14 abstentions is more caution than the spec wants and the gap is a contract conflict I have not resolved: the seeds record an unmentioned negative as `False`, the prompt says null means the text does not say, and span validation nulls anything without a verbatim quote.

### 3. Twenty seeds. Your own plan said 150. **WEAKNESS**

There are now 150 reverse-generated rows in `data/enquiries_150.csv`, with 50 held out in `data/call_batch.csv` as a 15/20/15 easy/medium/hard mix, and I can run any one of them with `python -m intake_triage run --id HG-2026-0011`. The weakness that remains is that those labels still come from `score.py`, so this is a larger consistency set, not an independent eval, and I would not quote live accuracy from it.

### 4. You have never seen the actual intake form. **WEAKNESS**

Correct, and that is why "what platform is the form and can fields be added" is one of the first five questions in CLARIFYING_QUESTIONS.md rather than something I assumed away. The specific risk is that industry, size, and urgency turn out to be free text rather than picklists, which raises the null rate, raises abstention, and changes the extraction prompt but not the two-layer split.

### 5. Thirty percent abstention means a human still reads a third of everything. Where is the win?

The 30% is on a seed set I deliberately weighted toward collisions and injections, so it is a ceiling on hard cases, not a forecast of live traffic. Even taken at face value it is 50 x 30% x 10 minutes = 2.5 hours/week against an 8 hour baseline, and the abstentions arrive pre-scored with two candidates so the human decision is a one-word reply rather than a fresh read.

### 6. Your injection defence is two literal phrases in a YAML file. I can bypass that in one try. **WEAKNESS**

You can, and the phrase list is a tripwire for the obvious case, not the defence. The actual defence is architectural: the model has no tool that can route, send, or set a tier; unevidenced spans are nulled; any remaining null scoring driver abstains rather than guessing. A successful injection can still produce a wrong fact, which is why this stays a WEAKNESS.

### 7. The hour constants are invented. Why should a partner trust 80 base hours for M&A?

They should not, and every constant in `policy.yaml` carries a comment saying it is a starting value pending calibration. The design point is that they are in a YAML file a partner can read and change in an afternoon rather than inside a prompt or a set of weights, so being wrong about them is a config edit rather than a rebuild.

### 8. Why not let the model just output complexity? It would probably be fine.

Probably fine is the problem: complexity, service line, hours, and routing are the four outputs someone has to defend to a paying client, and "the model said so" is not a defensible answer. Splitting them out costs some accuracy on genuinely ambiguous cases and buys a rule trace with quoted evidence, which is what makes a wrong answer diagnosable instead of just wrong.

### 9. No agent loop, no RAG, no fine-tuning. Is that judgment or is it scope?

Judgment, and each has a specific reason: there is no corpus to retrieve from, ~2,600 examples/year against a taxonomy that will change is the wrong shape for fine-tuning, and an agent loop adds nondeterminism to a problem whose hard part is that the taxonomy boundaries are undefined. If the taxonomy stabilises and volume goes past roughly 500/week, the fine-tuning argument changes and I would revisit it.

### 10. A lead leaves, or the firm adds a service line. What breaks?

The routing table, which is why it is nine lines of YAML rather than logic, and why the decision log stamps model and prompt version on every row so a metric shift after a change is attributable rather than arguable. What does not survive a taxonomy change is the calibration, so any line added or merged resets the constants for the affected lines and puts them back into shadow mode.

---

## If they follow up

### Your first live run abstained on everything. What did you change? **WEAKNESS**

The abstention rule was counting blank drivers, and at a threshold of one blank it abstained on every enquiry including ones where every driver was extracted correctly with a valid span. I replaced the count with a materiality test: an unknown blocks a committed tier only when it could move the hours across a tier boundary, so a missing systems flag abstains on a 30h matter that could reach 40h and commits on a 95h matter that cannot leave complex, and the count survives only as a backstop for letters too sparse to triage.

### What happens when the model is down?

Any failure abstains as `extraction_failed` and writes an email and a JSON copy under `data/out/review/` for a human, so an enquiry is never dropped because a field would not parse or an API call returned 401. The reason code matters as much as the routing: an outage and a genuinely terse letter both produce an abstention, and if they carry the same label the analyst cannot tell a bad week from an incident.

## Two things to volunteer before being asked

Seed 11 abstains and seed 12 does not, purely because one lead happens to own two service lines. That is a policy choice sitting in a file, not model behaviour, and it exposes that the taxonomy has boundaries nobody has defined.

The 10 minutes per enquiry figure (8 hours / 50) is the number that reframes the job. Nobody needs 10 minutes to pick a service line off a list, so the analyst is doing something the brief does not describe, and finding out what that is matters more than any accuracy number in this repo.
