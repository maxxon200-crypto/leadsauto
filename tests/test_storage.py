from leadsauto.models import Lead
from leadsauto.storage import CsvStore, SqliteStore, open_store


def test_csv_roundtrip(tmp_path):
    path = tmp_path / "leads.csv"
    store = CsvStore(path)
    leads = [Lead(name="Anna", email="a@b.it", city="Milano"),
             Lead(studio="Studio X", website="x.it")]
    assert store.write(leads) == 2

    back = store.read()
    assert len(back) == 2
    assert back[0].name == "Anna"
    assert back[1].website == "https://x.it"


def test_csv_append(tmp_path):
    path = tmp_path / "leads.csv"
    CsvStore(path).write([Lead(name="A", email="a@x.it")])
    CsvStore(path, append=True).write([Lead(name="B", email="b@x.it")])
    rows = CsvStore(path).read()
    assert [r.name for r in rows] == ["A", "B"]


def test_sqlite_upsert(tmp_path):
    path = tmp_path / "leads.sqlite"
    store = SqliteStore(path)
    store.write([Lead(name="Anna", email="a@b.it")])
    # Same email -> upsert, not a second row.
    store.write([Lead(name="Anna", email="a@b.it", phone="0212345")])
    rows = store.read()
    assert len(rows) == 1
    assert rows[0].phone == "0212345"


def test_open_store_infers_format(tmp_path):
    assert isinstance(open_store(tmp_path / "x.csv"), CsvStore)
    assert isinstance(open_store(tmp_path / "x.sqlite"), SqliteStore)
    assert isinstance(open_store(tmp_path / "x.out", fmt="csv"), CsvStore)
