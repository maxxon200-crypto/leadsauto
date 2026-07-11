from leadsauto.enrich import extract_emails, extract_phones, enrich_lead
from leadsauto.models import Lead


def test_extract_emails_filters_assets():
    text = "Write to info@studio.it or sales@studio.it. Logo: banner@2x.png"
    emails = extract_emails(text)
    assert "info@studio.it" in emails
    assert "sales@studio.it" in emails
    assert all("png" not in e for e in emails)


def test_extract_emails_dedupes_and_lowercases():
    assert extract_emails("Info@X.IT info@x.it") == ["info@x.it"]


def test_extract_phones_italian():
    text = "Tel +39 02 1234 5678 oppure 345 678 9012"
    phones = extract_phones(text)
    assert any(p.startswith("+39") for p in phones)
    assert any(p == "3456789012" for p in phones)


class FakeClient:
    """Stand-in HttpClient that serves canned HTML per URL."""

    def __init__(self, pages: dict[str, str]):
        self.pages = pages
        self.requested: list[str] = []

    def get_text(self, url: str) -> str:
        self.requested.append(url)
        for key, html in self.pages.items():
            if url.rstrip("/").endswith(key.rstrip("/")) or url == key:
                return html
        raise Exception("404")


def test_enrich_lead_from_homepage():
    lead = Lead(website="https://studio.example")
    client = FakeClient({
        "https://studio.example": (
            "<html><body>Contatti: "
            "<a href='mailto:hello@studio.example'>email</a> "
            "Tel 02 9999 1111</body></html>"
        )
    })
    enrich_lead(lead, client)
    assert lead.email == "hello@studio.example"
    assert lead.phone == "0299991111"


def test_enrich_skips_when_already_complete():
    lead = Lead(website="https://x.it", email="a@x.it", phone="0212345")
    client = FakeClient({})
    enrich_lead(lead, client)
    assert client.requested == []  # no network calls needed
