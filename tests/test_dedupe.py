from leadsauto.dedupe import dedupe, dedupe_key
from leadsauto.models import Lead


def test_key_prefers_email():
    assert dedupe_key(Lead(email="a@b.it", website="x.it")) == "email:a@b.it"


def test_key_falls_back_to_domain_then_name():
    assert dedupe_key(Lead(website="https://www.studio.it")) == "site:studio.it"
    assert dedupe_key(Lead(name="Mario Rossi", city="Roma")) == "name:mario rossi|roma"
    assert dedupe_key(Lead()) is None


def test_dedupe_merges_on_email():
    leads = [
        Lead(name="Anna", email="a@b.it", city="Milano"),
        Lead(name="Anna", email="a@b.it", phone="0212345", address="Via Roma 1"),
    ]
    out = dedupe(leads)
    assert len(out) == 1
    assert out[0].phone == "0212345"
    assert out[0].address == "Via Roma 1"
    assert out[0].city == "Milano"


def test_dedupe_name_accent_insensitive():
    leads = [
        Lead(name="Niccolò Verdì", city="Torino"),
        Lead(name="Niccolo Verdi", city="Torino", phone="0111111"),
    ]
    out = dedupe(leads)
    assert len(out) == 1
    assert out[0].phone == "0111111"


def test_dedupe_keeps_unkeyable_rows():
    leads = [Lead(phone="0212345"), Lead(phone="0298765")]
    # phone-only leads have no stable key -> both preserved
    assert len(dedupe(leads)) == 2
