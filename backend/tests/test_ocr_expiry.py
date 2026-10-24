from __future__ import annotations

from datetime import date

from app.services.ocr import parse_expiry_candidates

TODAY = date(2025, 3, 1)


def best(text: str) -> date | None:
    candidates = parse_expiry_candidates(text, today=TODAY)
    return candidates[0].value if candidates else None


def all_dates(text: str) -> list[date]:
    return [c.value for c in parse_expiry_candidates(text, today=TODAY)]


def test_reads_a_plain_uk_date():
    assert best("BEST BEFORE 15/03/2025") == date(2025, 3, 15)


def test_two_digit_years_are_this_century():
    assert best("USE BY 15.03.25") == date(2025, 3, 15)


def test_reads_a_written_month():
    assert best("BEST BEFORE 20 MAR 2025") == date(2025, 3, 20)


def test_month_and_year_only_means_end_of_month():
    assert best("BEST BEFORE END MAR 2025") == date(2025, 3, 31)
    assert best("BBE 04/25") == date(2025, 4, 30)


def test_iso_dates_are_understood():
    assert best("EXP 2025-06-30") == date(2025, 6, 30)


def test_an_ambiguous_date_offers_both_readings_day_first():
    # 03/04/25 is 3 April to most of the world and 4 March in the US. Offer both,
    # but lead with day-first rather than silently picking one.
    assert all_dates("BEST BEFORE 03/04/25")[:2] == [date(2025, 4, 3), date(2025, 3, 4)]


def test_an_unambiguous_date_is_not_doubled_up():
    assert all_dates("BEST BEFORE 25/12/25") == [date(2025, 12, 25)]


def test_the_hinted_date_beats_a_packed_on_date():
    text = "PACKED 20/02/2025\nBEST BEFORE 10/04/2025"
    assert best(text) == date(2025, 4, 10)


def test_without_a_hint_the_soonest_future_date_wins():
    assert best("10/06/2025  04/04/2025") == date(2025, 4, 4)


def test_dates_already_past_rank_below_future_ones():
    assert all_dates("01/01/2024 10/04/2025")[0] == date(2025, 4, 10)


def test_batch_codes_and_nonsense_are_ignored():
    assert all_dates("L3421 99/99/9999 BATCH 847362") == []


def test_dates_far_outside_a_shelf_life_are_rejected():
    # A 1998 date on a 2025 label is a misread, not a thirty-year-old yoghurt.
    assert all_dates("12/05/1998") == []


def test_no_text_yields_no_guesses():
    assert all_dates("") == []
    assert all_dates("BEST BEFORE SEE LID") == []


def test_hint_must_be_near_the_date_to_count():
    far = "USE BY" + " filler" * 20 + " 10/04/2025 01/04/2025"
    # The hint is too far away to attach, so the soonest future date leads instead.
    assert best(far) == date(2025, 4, 1)


def test_endpoint_reports_unavailable_rather_than_failing(client, monkeypatch):
    from app.api import scan as scan_api

    monkeypatch.setattr(scan_api, "ocr_available", lambda: False)
    response = client.post("/api/scan/expiry", files={"image": ("l.jpg", b"x", "image/jpeg")})
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["candidates"] == []


def test_endpoint_returns_ranked_candidates(client, monkeypatch):
    from datetime import timedelta

    from app.api import scan as scan_api

    packed = date.today() - timedelta(days=30)
    use_by = date.today() + timedelta(days=300)
    monkeypatch.setattr(scan_api, "ocr_available", lambda: True)
    monkeypatch.setattr(
        scan_api,
        "read_text",
        lambda _b: f"PACKED {packed:%d/%m/%Y}\nUSE BY {use_by:%d/%m/%Y}",
    )
    response = client.post("/api/scan/expiry", files={"image": ("l.jpg", b"x", "image/jpeg")})
    body = response.json()
    assert body["available"] is True
    assert body["candidates"][0]["date"] == use_by.isoformat()
    assert body["candidates"][0]["hinted"] is True
