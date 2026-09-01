# BUSINESS_CASE

Net of a loaded $35-50/hr assumption (A10, not in the brief), 416 analyst hours/year (8 x 52, derived from the brief) is about $15,000-21,000/year. That is the visible labour. It is not the whole case.

The larger and less visible cost is error. Misrouting delays first response. Response latency on an inbound enquiry is a conversion variable for a professional services firm. I cannot size that without their close-rate data. I would ask for: enquiry-to-first-response time, win rate by response bucket, and the last twenty misroutes with what wrong meant.

Cost of operation, with the arithmetic shown:

- Inference: ~2,600/year (50 x 52), ~2K in + 500 out tokens, up to 3 samples for abstention. At mid-tier hosted prices this lands around $100-500/year (A10/A11).
- Hosting: scale-to-zero container, $0-15/month, or $0 incremental on a tool they already own.
- Orchestration: $0 incremental if we use Gmail/Sheets or Outlook/Excel they already have.
- Human review: residual analyst time at the observed abstention rate, not 8 hours tagging.
- Maintenance: a few hours per quarter for taxonomy and policy updates. It is not zero.

Inference is under 1% of the labour it replaces. Cost optimisation is not the engineering priority. Any design that trades accuracy for token savings at this volume optimises the wrong variable.

The real enterprise cost is procurement. A new AI vendor means an MSA, a DPA, a security review, residency questions, and an owner for key rotation. For a firm this size that can exceed the value of the automation. Route through whatever cloud they already have. If they have none, say so rather than bury it. Assumption A7 in the prototype is Google Workspace. That is a fixture.

Payback, conservative: 2-3 days of FDE time against $15,000-21,000 labour, plus unquantified conversion effects. Even if loaded rate is half of A10, payback is weeks, not years, provided we do not add a vendor and a UI.
