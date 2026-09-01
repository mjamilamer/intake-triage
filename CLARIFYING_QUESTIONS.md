# CLARIFYING_QUESTIONS

The number that reframes the problem is not 8 hours. It is about 10 minutes. 8 hours across a working midpoint of 50 enquiries (derived from the brief's 40-60 range) is 10 minutes each. Nobody needs 10 minutes to pick from a short list of service lines. Hypothesis, not a conclusion: the analyst is reconstructing missing context and adjudicating an undefined complexity rubric. The questions below are designed to confirm or kill that hypothesis.

## Questions that change the BUILD

Where does the form post today? If it is already a CRM or a mailbox rule, we emit there. If it is an unowned inbox, email plus a ledger is the conservative path.

What platform is the form, and can fields be added? Optional picklists reduce nulls. Every added required field costs conversions. A lost professional-services enquiry may be worth thousands.

What does the team lead work in after routing? That is the only output surface that matters. We will not invent a queue they will not open.

Is M365, Google Workspace, or AWS already under contract? Assumption A7 in this prototype is Google Workspace, Gmail, and a Google Sheet named Intake 2026. That is not in the brief. If they are on M365, the adapters become Outlook and Excel. Score and route do not change.

Is there any stored history of past enquiries and their routing? If yes, shadow mode plus adjudication replaces synthetic labels (A13). If no, we keep synthetic data until week two of shadow.

## Questions that change the DESIGN

Who owns the taxonomy, and when did it last change? Five service lines in this repo (A3) are a working scenario. They are not a finding about the unnamed firm.

Show me the last twenty the analyst got wrong, and what wrong meant. Misroute, mistier, and slow first response are different losses.

Is there a written complexity rubric, or is it accumulated judgment (A12)? If a rubric exists, it belongs in policy.yaml. If not, scoring hours is how we write it down without pretending the model knows.

Who is accountable when something is misrouted today, and how do they find out? Reroute-after-assignment is the free error signal. If nobody records reroutes, we cannot calibrate.

Is the 8 hours one person or several, in one block or scattered? That changes whether compression frees a role or just fragments a bad afternoon.

## What does the analyst do with the other 32 hours?

This decides whether the project produces a redesign or a smaller version of the same job. If the 8 hours go back to incomplete enquiries and faster first response, we compressed into better work. If the 8 hours disappear into a layoff target, people will hide how the work actually gets done. Assumption A9 is residual review at 1-2 hours/week. Verify it.

## Assumptions table

See AGENTS.md for the full A1-A15 register. Minimum set the brief did not give us:

| Assumption | Why I made it | What breaks if wrong | How I verify in week one |
|---|---|---|---|
| A5 Form has picklists for industry, size, urgency | PDF says enquiries include those attributes | Extraction must take them from free text; nulls rise | Open the live form |
| A8 Email + spreadsheet + JSONL, no UI | PDF allows whatever we would actually reach for | If a CRM exists, emit there | Ask what the lead works in |
| A3 Five service lines are stable enough to prototype | PDF requires tagging by service line and lists none | Collisions change; two-layer design does not | Ask who owns the taxonomy |
| A13 No labelled history | PDF requires synthetic data | Gold set becomes real mail | Ask for the archive |
| A4 No CRM | PDF is silent on stack | Adapters change | Ask what the form posts to |
| A14 Volume stays under 100/week | PDF is 40-60 | A queue becomes justified | Trailing 12-week volume |
