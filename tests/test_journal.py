from intake_triage.journal import run_seed


def test_journal_seed_11_abstains():
    payload = run_seed("HG-2026-0011")
    assert payload["decision"]["abstained"] is True
    fired = [g["id"] for g in payload["gates"] if g["status"] == "fired"]
    assert fired[0] == "cross_lead"
    assert payload["intake"]["description"]
    assert "work_signals" in payload["extraction"]


def test_journal_seed_12_commits():
    payload = run_seed("HG-2026-0012")
    assert payload["decision"]["abstained"] is False
    assert payload["decision"]["service_line"] == "MA_TRANSACTION"
    fired = [g["id"] for g in payload["gates"] if g["status"] == "fired"]
    assert fired[-1] == "commit"


def test_journal_injection():
    payload = run_seed("HG-2026-0015")
    assert payload["decision"]["abstained"] is True
    fired = [g["id"] for g in payload["gates"] if g["status"] == "fired"]
    assert fired[0] == "injection"
    assert "partner" not in (payload["decision"]["route_to"] or "").lower()
