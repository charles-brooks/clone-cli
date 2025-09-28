from clone_audit import utils


def test_normalize_url_lowercases_and_strips_fragment():
    result = utils.normalize_url("HTTP://Example.COM/foo#section")
    assert result == "http://example.com/foo"


def test_canonical_path_keeps_query():
    path = utils.canonical_path("https://example.com/path?a=1")
    assert path == "/path?a=1"


def test_hamming_distance_zero_for_identical_hashes():
    assert utils.hamming_distance("ffffffffffffffff", "ffffffffffffffff") == 0


def test_tokenize_text_simple():
    tokens = utils.tokenize_text("Hello, Clone Auditor!")
    assert tokens == ["hello", "clone", "auditor"]
