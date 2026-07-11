from leadsauto.models import Lead, normalize_email, normalize_phone, normalize_website


def test_normalize_email():
    assert normalize_email("  Info@Studio.IT ") == "info@studio.it"
    assert normalize_email("a@b.com.") == "a@b.com"
    assert normalize_email(None) == ""


def test_normalize_phone_international_and_local():
    assert normalize_phone("+39 02 1234 5678") == "+390212345678"
    assert normalize_phone("0039 02 1234") == "+39021234"
    assert normalize_phone("02/1234.567") == "021234567"
    assert normalize_phone("") == ""


def test_normalize_website_adds_scheme_and_strips_slash():
    assert normalize_website("studio.it") == "https://studio.it"
    assert normalize_website("http://studio.it/") == "http://studio.it"
    assert normalize_website("mailto:a@b.com") == ""


def test_lead_normalizes_on_construction():
    lead = Lead(name="  Anna  ", email="A@B.IT", website="anna.it/")
    assert lead.name == "Anna"
    assert lead.email == "a@b.it"
    assert lead.website == "https://anna.it"


def test_is_empty():
    assert Lead().is_empty()
    assert not Lead(name="x").is_empty()
    assert not Lead(email="a@b.it").is_empty()


def test_merge_fills_blanks_only():
    a = Lead(name="Anna", email="a@b.it")
    b = Lead(name="Different", phone="0212345", website="anna.it")
    a.merge(b)
    assert a.name == "Anna"           # not overwritten
    assert a.phone == "0212345"       # filled
    assert a.website == "https://anna.it"


def test_row_roundtrip():
    lead = Lead(name="Anna", email="a@b.it", city="Milano")
    row = lead.to_row()
    restored = Lead.from_row(row)
    assert restored.name == "Anna"
    assert restored.email == "a@b.it"
    assert restored.city == "Milano"
