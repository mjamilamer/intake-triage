# BUSINESS_CASE

## Visible labour

Given: 8 analyst hours/week. Derived: 8 x 52 = 416 hours/year. Assumption, not in the brief: loaded analyst cost of $35-50/hr. 416 x $35 = $14,560 and 416 x $50 = $20,800, so roughly $15,000-21,000/year.

That is the part anyone can count, and it is the smaller half of the case.

## Invisible cost

The larger cost is error. A misroute delays first response, and response latency on an inbound enquiry is a conversion variable for a professional services firm. I cannot size it without their numbers, and I will not invent it. To size it I need three things: enquiry-to-first-response time, win rate bucketed by response time, and the last twenty misroutes with what "wrong" meant in each. If a single mid-size engagement is lost per year to slow routing, it likely exceeds the entire labour figure above.

## Cost to run

Given 40-60/week: 50 x 52 = ~2,600 enquiries/year.

- **Inference.** ~2,600 calls at roughly 2K input and 500 output tokens, up to 3 samples on ambiguous cases. At mid-tier hosted pricing that is on the order of $100-500/year.
- **Hosting.** Scale-to-zero container at $0-15/month, or $0 incremental on a tool they already own.
- **Orchestration.** $0 incremental. It writes to the mail and spreadsheet they already pay for.
- **Human review.** Residual analyst time set by the observed abstention rate, not 8 hours of tagging.
- **Maintenance.** A few hours per quarter for taxonomy and policy changes. Not zero, and the number that grows if the taxonomy is unstable.

Inference is under 1% of the labour it replaces. That is the point worth making: at 2,600 calls/year, cost optimisation is not an engineering priority. Any design that trades accuracy for token savings at this volume is optimising the wrong variable.

## The cost that actually kills projects

Procurement. A new AI vendor means an MSA, a DPA, a security review, a residency answer, and a named owner for key rotation. Assumption, not in the brief: a ~90-person boutique. At that size the process can cost more than the automation returns. Route through a cloud they already hold. If they hold none, say so out loud in week one rather than discovering it at signature.

## Payback

Two to three days of FDE time against $15,000-21,000/year of visible labour, plus conversion effects I have not sized. Even at half the assumed loaded rate, payback is weeks, on one condition: we do not add a vendor and we do not build a UI. Both of those are how a project this size turns into a project that needs a budget.
