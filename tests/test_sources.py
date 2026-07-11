from leadsauto.sources import get_source, builtin_names, load_config_sources
from leadsauto.sources.generic_directory import GenericDirectorySource


def test_sample_source_returns_leads():
    src = get_source("sample")
    leads = list(src.search("milano", limit=10))
    assert leads
    assert all(lead.source == "sample" for lead in leads)
    # query filters by city
    assert all("milano" in " ".join(
        [lead.city.lower(), lead.name.lower(), lead.studio.lower()]
    ) for lead in leads)


def test_sample_source_registered():
    assert "sample" in builtin_names()


FIXTURE_HTML = """
<html><body>
  <div class="professional-card">
    <h3 class="pro-name">Giulia Ferrari</h3>
    <span class="pro-studio">Studio Ferrari</span>
    <a class="pro-email" href="mailto:g@ferrari.example">email</a>
    <span class="pro-phone">+39 02 1234 5678</span>
    <a class="pro-website" href="https://ferrari.example">web</a>
    <span class="pro-city">Milano</span>
  </div>
  <div class="professional-card">
    <h3 class="pro-name">Marco Bianchi</h3>
    <span class="pro-phone">02 8765 4321</span>
    <span class="pro-city">Milano</span>
  </div>
</body></html>
"""


class OnePageClient:
    def __init__(self, html):
        self.html = html
        self.calls = 0

    def get_text(self, url):
        self.calls += 1
        # Return results on the first page only, empty on later pages.
        return self.html if self.calls == 1 else "<html><body></body></html>"


def test_generic_directory_parses_config():
    config = {
        "search_url": "https://d.example/s?q={query}&p={page}",
        "list_selector": "div.professional-card",
        "max_pages": 3,
        "fields": {
            "name": {"selector": "h3.pro-name"},
            "studio": {"selector": ".pro-studio"},
            "email": {"selector": "a.pro-email", "attr": "href", "strip_prefix": "mailto:"},
            "phone": {"selector": ".pro-phone"},
            "website": {"selector": "a.pro-website", "attr": "href"},
            "city": {"selector": ".pro-city"},
        },
        "defaults": {"profession": "Architetto", "country": "IT"},
    }
    src = GenericDirectorySource("test_dir", config, client=OnePageClient(FIXTURE_HTML))
    leads = list(src.search("milano", limit=100))

    assert len(leads) == 2
    g = leads[0]
    assert g.name == "Giulia Ferrari"
    assert g.email == "g@ferrari.example"
    assert g.phone == "+390212345678"
    assert g.website == "https://ferrari.example"
    assert g.profession == "Architetto"
    assert g.source == "test_dir"


def test_generic_directory_respects_limit():
    config = {
        "search_url": "https://d.example/s?q={query}&p={page}",
        "list_selector": "div.professional-card",
        "fields": {"name": {"selector": "h3.pro-name"}},
    }
    src = GenericDirectorySource("test_dir", config, client=OnePageClient(FIXTURE_HTML))
    assert len(list(src.search("milano", limit=1))) == 1


def test_load_config_sources():
    config = {"sources": {"d1": {
        "search_url": "https://x/{query}/{page}",
        "list_selector": ".card",
    }}}
    sources = load_config_sources(config)
    assert "d1" in sources
    assert isinstance(sources["d1"], GenericDirectorySource)
