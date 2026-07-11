from leadsauto.pipeline import run
from leadsauto.sources import get_source
from leadsauto.storage import CsvStore


def test_pipeline_scrape_dedupe_store(tmp_path):
    src = get_source("sample")
    out = tmp_path / "leads.csv"
    store = CsvStore(out)

    result = run(src, query="", limit=100, enrich=False, dedupe=True, store=store)

    # Sample data has 4 rows, two of which share an email -> 3 after dedupe.
    assert result.scraped == 4
    assert result.after_dedupe == 3
    assert result.written == 3

    rows = store.read()
    assert len(rows) == 3
    # Merged lead should have picked up the address from the duplicate.
    giulia = [r for r in rows if r.email == "info@ferrari-arch.example"]
    assert giulia and giulia[0].address == "Via Roma 12"


def test_pipeline_without_dedupe(tmp_path):
    src = get_source("sample")
    result = run(src, query="", limit=100, dedupe=False)
    assert result.after_dedupe == 4
