"""Journal packs, form-empty email, and cache roundtrip."""

from intake_triage.journal import INTERVIEW_IDS, TEST_IDS, list_cases, list_seeds, pack_counts, run_seed


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


def test_interview_pack_covers_csv_examples():
    rows = list_cases("interview")
    ids = [r["enquiry_id"] for r in rows]
    assert ids == [eid for eid in INTERVIEW_IDS if eid in ids]
    assert len(rows) == 26
    assert any(r["enquiry_id"] == "HG-2026-0201" for r in rows)
    assert any(r["enquiry_id"] == "HG-2026-0205" for r in rows)
    assert any(r["difficulty"] == "very_hard" for r in rows)
    assert any(r["source"] == "generated" for r in rows)
    assert any(r["enquiry_id"] == "HG-2026-0127" for r in rows)
    assert pack_counts()["call"] == 50
    assert pack_counts()["all"] == 150
    call = list_cases("call")
    assert len(call) == 50
    csv_ids = {r["enquiry_id"] for r in rows if not r["enquiry_id"].startswith("HG-2026-02")}
    assert csv_ids <= {r["enquiry_id"] for r in list_cases("all")}


def test_journal_runs_generated_csv_example():
    payload = run_seed("HG-2026-0127")
    assert payload["record_source"] == "generated"
    assert payload["extraction_source"] == "reverse_generated"
    assert payload["intake"]["company_name"]
    assert payload["extraction"]["work_signals"]


def test_intake_card_has_no_extraction():
    from intake_triage.journal import intake_card

    card = intake_card("HG-2026-0011")
    assert card["description"]
    assert "extraction" not in card


def test_compare_without_key_keeps_authored_before():
    from intake_triage.journal import run_compare

    result = run_compare("HG-2026-0001")
    assert result["before"]["extraction_source"] == "authored_drivers"
    assert result["before"]["decision"]["service_line"] == "TAX_STRUCTURING"
    if not result["after"]["llm_status"]["has_llm_key"]:
        assert result["after"]["extraction_source"] == "failed"


def test_journal_cases_are_grouped():
    rows = list_seeds()
    assert len(rows) == 20
    assert {r["group"] for r in rows} == {"panel", "clean", "held", "edge"}
    panel = [r for r in rows if r["group"] == "panel"]
    assert {r["enquiry_id"] for r in panel} == {"HG-2026-0011", "HG-2026-0012", "HG-2026-0015"}
    assert all("why" in r and "outcome" in r for r in rows)
    assert "label" not in rows[0]


def test_test_pack_includes_long_and_free_text():
    from intake_triage.journal import LONG_IDS, TEST_IDS
    from intake_triage.journal_extras import FREE_TEXT_IDS

    rows = list_cases("test")
    ids = {r["enquiry_id"] for r in rows}
    assert set(LONG_IDS) <= ids
    assert set(FREE_TEXT_IDS) <= ids
    assert len(rows) == len({eid for eid in TEST_IDS})
    long_row = next(r for r in rows if r["enquiry_id"] == LONG_IDS[0])
    assert "Long prompt" in long_row["why"]
    free = next(r for r in rows if r["enquiry_id"] == FREE_TEXT_IDS[0])
    assert free["form_empty"] is True


def test_free_text_uses_size_from_letter():
    payload = run_seed("HG-2026-0213")
    assert payload["form_empty"] is True
    assert payload["intake"]["company_name"] is None
    assert payload["intake"]["industry"] is None
    assert payload["decision"]["service_line"] == "TAX_STRUCTURING"
    assert payload["extraction"]["stated_company"]["value"] == "Whitcombe Holdings"
    assert "Whitcombe Holdings (from letter)" in payload["email"]
    assert "professional_services (from letter)" in payload["email"]
    assert "sme (from letter)" in payload["email"]
    assert "normal (from letter)" in payload["email"]
    assert "Brief (from letter):" in payload["email"]
    assert "I am FD at Whitcombe Holdings" in payload["email"]
    assert payload["sheet_row"]["company_name"] == "Whitcombe Holdings"
    assert payload["sheet_row"]["industry"] == "professional_services"
    assert payload["sheet_row"]["company_size"] == "sme"
    assert payload["sheet_row"]["urgency"] == "normal"


def test_form_picklists_win_over_letter():
    payload = run_seed("HG-2026-0001")
    assert "(from letter)" not in payload["email"]
    assert "Brief (from letter):" not in payload["email"]
    assert payload["sheet_row"]["company_name"] == payload["intake"]["company_name"]


def test_hard_and_very_hard_extras_score():
    hard = run_seed("HG-2026-0201")
    assert hard["decision"]["abstained"] is False
    assert hard["decision"]["service_line"] == "MA_TRANSACTION"
    very = run_seed("HG-2026-0205")
    assert very["decision"]["abstain_reason"] == "out_of_taxonomy"
    three = run_seed("HG-2026-0206")
    assert three["decision"]["abstain_reason"] == "cross_lead_conflict"


def test_cache_roundtrip(tmp_path, monkeypatch):
    from intake_triage import journal as journal_mod

    monkeypatch.setattr(journal_mod, "CACHE_DIR", tmp_path)
    payload = run_seed("HG-2026-0001")
    journal_mod.save_cached("HG-2026-0001", "run", payload)
    loaded = journal_mod.load_cached("HG-2026-0001")
    assert loaded["kind"] == "run"
    assert loaded["payload"]["decision"]["service_line"] == "TAX_STRUCTURING"
    assert "HG-2026-0001" in journal_mod.cached_ids()
    card = journal_mod.intake_card("HG-2026-0001")
    assert card["has_last"] is True
    assert card["form_filled"]["company_name"] == "Northbridge Payroll Ltd"
