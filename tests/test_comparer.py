from clone_audit.comparer import Comparer
from clone_audit.config import ComparisonConfig
from clone_audit.models import CrawlResult, ImageArtifact, SiteArtifacts, StructureSignature, TextArtifact


def build_site(texts=None, images=None, structures=None):
    texts = texts or []
    images = images or []
    structures = structures or []
    crawl = CrawlResult(root_url="https://example.com", snapshots=[])
    return SiteArtifacts(crawl=crawl, texts=list(texts), images=list(images), structures=list(structures))


def test_text_similarity_detects_high_match():
    comparer = Comparer(ComparisonConfig())
    base = build_site(
        texts=[TextArtifact(page_url="https://legit", locator="body/p", text="Welcome to our secure portal", token_count=5)]
    )
    clone = build_site(
        texts=[TextArtifact(page_url="https://clone", locator="body/p", text="Welcome to our secure portal", token_count=5)]
    )
    result = comparer.compare(base, clone)
    assert result.breakdown.text_score == 1.0
    assert result.text_matches
    assert result.text_matches[0].high_confidence is True


def test_image_similarity_aggregates_scores():
    comparer = Comparer(ComparisonConfig(weight_text=0.0, weight_images=1.0, weight_structure=0.0))
    base = build_site(images=[ImageArtifact(page_url="https://legit", url="https://legit/logo.png", hash_bits="ffffffffffffffff", bytes_size=10, content_type="image/png")])
    clone = build_site(images=[ImageArtifact(page_url="https://clone", url="https://clone/logo.png", hash_bits="ffffffffffffffff", bytes_size=10, content_type="image/png")])
    result = comparer.compare(base, clone)
    assert result.breakdown.image_score == 1.0
    assert result.breakdown.overall_score == 1.0


def test_structure_similarity_uses_jaccard():
    comparer = Comparer(ComparisonConfig(weight_text=0.0, weight_images=0.0, weight_structure=1.0))
    base_struct = StructureSignature(page_url="https://legit", depth=0, tag_sequence=("html", "body", "div", "p"))
    clone_struct = StructureSignature(page_url="https://clone", depth=0, tag_sequence=("html", "body", "div", "span"))
    base = build_site(structures=[base_struct])
    clone = build_site(structures=[clone_struct])
    result = comparer.compare(base, clone)
    assert result.breakdown.structure_score == 0.6


def test_text_similarity_deduplicates_identical_snippets():
    comparer = Comparer(ComparisonConfig(text_threshold=0.5))
    text = "Click here to claim your reward now!"
    base_texts = [
        TextArtifact(page_url="https://legit", locator="body/div[1]", text=text, token_count=6),
        TextArtifact(page_url="https://legit", locator="body/div[2]", text=text, token_count=6),
    ]
    clone_texts = [
        TextArtifact(page_url="https://clone", locator="body/div[1]", text=text, token_count=6),
    ]
    base = build_site(texts=base_texts)
    clone = build_site(texts=clone_texts)
    result = comparer.compare(base, clone)
    assert len(result.text_matches) == 1
