# CLARIFYING_QUESTIONS

The number that reframes the problem is not 8 hours. It is 10 minutes.

Given: 40-60 enquiries/week, 8 analyst hours/week. Derived: midpoint (40+60)/2 = 50 per week, 8 hours / 50 = 0.16h = about 10 minutes per enquiry. Nobody needs 10 minutes to pick a service line off a short list. So either the analyst is reconstructing context the form failed to capture, or they are adjudicating a complexity rubric nobody has written down, or the 8 hours is a self-reported estimate that includes chasing incomplete enquiries. Those three have different fixes. That is a hypothesis, not a finding, and the first five questions are built to kill it.

## Questions that change the BUILD

**Where does the form post today?** If it lands in a CRM or a mailbox rule, we emit there. If it lands in an unowned inbox, email plus a ledger is the conservative path. This is the single answer that most changes what gets written.

**What platform is the form, and can fields be added?** Optional picklists cut nulls at zero cost. Required fields cut conversions, and one lost professional-services enquiry can be worth more than a year of this system.

**What does the team lead actually open after routing?** That is the only output surface that matters. We will not invent a queue nobody logs into.

**Is M365, Google Workspace, or a cloud already under contract?** Assumption, not in the brief: this prototype writes to Gmail and a Google Sheet. On M365 the adapters become Outlook and Excel. Score and route are untouched. This matters because a new vendor means an MSA, a DPA, and a security review, which for a firm this size can cost more than the automation saves.

**Is there stored history of past enquiries and how they were routed?** If yes, shadow mode plus adjudication gives us a real gold set in two weeks and the synthetic data is scaffolding we throw away. If no, we stay synthetic until week two of shadow.

## Questions that change the DESIGN

**Who owns the taxonomy, and when did it last change?** Assumption, not in the brief: the five service lines in this repo are a working scenario, invented so there is something to score. They are not a finding about the firm. If the real taxonomy has twelve lines with overlapping ownership, the collision behaviour changes and the two-layer split does not.

**Show me the last twenty the analyst got wrong, and what "wrong" meant.** Misroute, mis-tier, and slow first response are three different losses with three different fixes. Optimising the wrong one is the main way this project fails quietly.

**Is there a written complexity rubric, or is it accumulated judgment?** If a rubric exists it belongs in `policy.yaml` on day one. If it does not, scoring to hours is how we write it down without pretending a model knows.

**Who is accountable when something is misrouted today, and how do they find out?** Reroute-after-assignment is the free error signal and the truest one. If nobody records reroutes, we cannot calibrate, and I would add that logging before I add anything else.

**Is the 8 hours one person or several, in one block or scattered?** That decides whether compression frees a role or just fragments a bad afternoon differently.

## The question behind the project

**What does the analyst do with the other 32 hours?** If the 8 hours go back into chasing incomplete enquiries and faster first response, we compressed work into better work. If the 8 hours are a layoff target, people will hide how the work actually gets done and the error signal we depend on dries up. Assumption, not in the brief: residual review at 1-2 hours/week, not zero. Verify this before building, not after.

## Assumptions that change the build

Full A1-A15 register in [AGENTS.md](AGENTS.md). The four that would change code:

| Assumption | Why | What breaks if wrong | Verified by |
|---|---|---|---|
| Industry, size, urgency are picklists, not free text | Brief says enquiries "include" them, not how | Extraction must recover them from prose; null rate rises and abstention rises with it | Open the live form |
| Email plus spreadsheet plus JSONL, no UI | Brief allows notebook, app, or orchestration | If a CRM exists we emit there instead | Ask what the lead opens |
| Five service lines, four leads, one lead owning two lines | Brief requires tagging by service line and lists none | Collision and abstain rules change; the two-layer design does not | Ask who owns the taxonomy |
| No labelled history exists | Brief requires synthetic data | Gold set becomes real mail in week one and the synthetics are discarded | Ask for the archive |
