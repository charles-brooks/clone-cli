from clone_audit.comparer import Comparer
from clone_audit.config import ComparisonConfig, ReportConfig
from clone_audit.models import (
    CrawlResult,
    HostingRecord,
    SiteArtifacts,
    TextArtifact,
    WhoisRecord,
)
from clone_audit.report import ReportBuilder
from types import SimpleNamespace


def build_site(url: str, text: str) -> SiteArtifacts:
    crawl = CrawlResult(root_url=url, snapshots=[])
    text_artifact = TextArtifact(page_url=url, locator="body/p", text=text, token_count=len(text.split()))
    return SiteArtifacts(crawl=crawl, texts=[text_artifact])


def test_report_contains_similarity_summary():
    base_site = build_site("https://legit.example", "Secure login portal")
    clone_site = build_site("https://clone.example", "Secure login portal")
    comparison = Comparer(ComparisonConfig()).compare(base_site, clone_site)
    base_whois = WhoisRecord(domain="legit.example", registrar="Example Registrar", creation_date=None, updated_date=None, expiration_date=None)
    clone_whois = WhoisRecord(domain="clone.example", registrar=None, creation_date=None, updated_date=None, expiration_date=None, error="Lookup failed")
    base_hosting = HostingRecord(
        domain="legit.example",
        ip="203.0.113.10",
        network_name="ExampleNet",
        organization="BaseHost",
        country="US",
        source="https://rdap.example/ip/203.0.113.10",
        raw=None,
        error=None,
    )
    clone_hosting = HostingRecord(
        domain="clone.example",
        ip=None,
        network_name=None,
        organization=None,
        country=None,
        source=None,
        raw=None,
        error="RDAP lookup failed",
    )
    analysis = SimpleNamespace(
        base=base_site,
        clone=clone_site,
        comparison=comparison,
        base_whois=base_whois,
        clone_whois=clone_whois,
        base_hosting=base_hosting,
        clone_hosting=clone_hosting,
    )
    builder = ReportBuilder(ReportConfig())
    markdown = builder.build_markdown(analysis)
    assert "Clone Similarity Report" in markdown
    assert "Overall similarity" in markdown
    assert "Error: Lookup failed" in markdown
    assert "Hosting Providers" in markdown
    assert "BaseHost" in markdown
    assert "RDAP lookup failed" in markdown
