"""Deterministic tests for the user's original, byte-unchanged ingestion scripts."""

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from contract_qa.ingest import (
    build_chunks, chunk_contract, find_headings, load_contracts,
    is_successor, normalize,
)
from scripts import download_cuad

ROOT = Path(__file__).resolve().parents[1]


def labels(text):
    return [heading.section_id for heading in find_headings(normalize(text))]


def test_normalize_collapses_edgar_spacing_preserves_wrapped_lines():
    assert normalize("  The  Company\tshall\n pay\u00a0cash. \n\n Next   clause. ") == "The Company shall\npay cash.\n\nNext clause.\n"


def test_normalize_drops_page_numbers_and_source_lines():
    assert normalize("First\n\n12\nSource: SEC filing\nPage 3 of 4\n- 5 -\n\nSecond") == "First\n\nSecond\n"


@pytest.mark.parametrize("text", ["", "  ", "Text\r\n\r\nmore", "A \t B\n\n\nC", "1. Heading\nWrapped text.\n\nSource: SEC\n2"])
def test_normalize_idempotent(text):
    assert normalize(normalize(text)) == normalize(text)


@pytest.mark.parametrize("before,after,expected", [
    ((4, 1), (4, 1, 1), True), ((4, 1), (4, 2), True),
    ((4, 1), (5,), True), ((4, 1), (5, 1), True),
    ((4, 1, 2), (4, 2), True), ((4, 1, 2), (4, 1, 3), True),
    ((4,), (4, 1), True), ((4, 9), (4, 10), True),
    ((4, 1), (4, 1), False), ((4, 1), (4, 3), False),
    ((4, 1), (6, 1), False), ((4, 1), (3, 2), False),
    ((4, 1), (4, 1, 2), False), ((4, 1), (5, 2), False),
    ((4, 1), (4, 10), False), ((1,), (30,), False),
    (None, (1,), True), (None, (2,), True),
    (None, (2, 1), True), (None, (3,), False), (None, (1, 2), False),
])
def test_is_successor_truth_table(before, after, expected):
    assert is_successor(before, after) is expected


def test_headings_trust_paragraph_start_despite_numbering_gaps():
    assert labels("4.1 Scope. Details.\n\n9.3 Payment. Details.") == ["4.1", "9.3"]


def test_wrapped_days_are_not_headings():
    assert labels("1. Payment\nThe fee is due within\n30 days after receipt.\n\n30 days are allowed.") == ["1"]


def test_flattened_numbering_sequence_is_recovered():
    text = "4.1 Scope. A party agrees. 4.1.1 Detail. More text. 4.2 Payment. More. 5. Term. More. 5.1 Renewal."
    assert labels(text) == ["4.1", "4.1.1", "4.2", "5", "5.1"]


def test_flattened_first_heading_can_start_after_preamble():
    assert labels("This is the agreement. 1. Scope. Work. 1.1 Details. Work. 2. Fees.") == ["1", "1.1", "2"]


def test_cross_references_rejected_even_if_number_is_successor():
    assert labels("4.1 Scope. Pursuant to Section 4.2 Payment applies. 4.2 Fees. Pay now.") == ["4.1", "4.2"]


def test_cross_reference_jump_rejected():
    assert labels("4.1 Scope. As described pursuant to Section 6.1 Remedies apply. 4.2 Fees.") == ["4.1", "4.2"]


def test_article_resynchronizes_after_table_of_contents():
    text = "9.9 Last Contents Entry\n\nARTICLE IV RIGHTS 4.1 Scope. Details. 4.2 Fees."
    assert labels(text) == ["9.9", "Article IV", "4.1", "4.2"]


def test_arabic_article_and_section_prefix():
    assert labels("ARTICLE 2 Terms\n\nSection 2.1 Obligations. 2.2 Fees.") == ["Article 2", "2.1", "2.2"]


def assert_lossless(chunks, text):
    assert len({chunk.chunk_id for chunk in chunks}) == len(chunks)
    last_end = 0
    for chunk in chunks:
        assert chunk.text == text[chunk.char_start:chunk.char_end]
        assert 0 < len(chunk.text) <= 4000
        assert chunk.char_start >= last_end
        assert not text[last_end:chunk.char_start].strip()
        last_end = chunk.char_end
    assert not text[last_end:].strip()
    assert "".join("".join(chunk.text.split()) for chunk in chunks) == "".join(text.split())


def test_chunk_slice_invariant_and_duplicate_id_suffixes():
    text = normalize("\n\n".join("1. Scope. " + "Some binding terms. " * 10 for _ in range(3)))
    chunks = chunk_contract("demo", text)
    assert [chunk.chunk_id for chunk in chunks] == ["demo::1", "demo::1~2", "demo::1~3"]
    assert_lossless(chunks, text)


def test_heading_only_sections_merge_forward():
    text = normalize("1. PURPOSE\n\n1.1 Scope. " + "The parties provide services. " * 5 + "\n\n2. Fees. " + "Payment is required. " * 6)
    chunks = chunk_contract("demo", text)
    assert len(chunks) == 2
    assert chunks[0].text.startswith("1. PURPOSE\n\n1.1 Scope.")
    assert chunks[0].method == "section"
    assert_lossless(chunks, text)


def test_oversized_sections_split_at_paragraphs():
    text = normalize("1. Terms. " + "alpha " * 400 + "\n\n" + "beta " * 450 + "\n\n" + "gamma " * 450 + "\n\n2. Fees. " + "Terms. " * 20 + "\n\n3. Term. " + "Terms. " * 20)
    chunks = chunk_contract("demo", text)
    assert chunks[0].text.endswith("alpha")
    assert chunks[0].chunk_id == "demo::1#p1"
    assert chunks[1].chunk_id == "demo::1#p2"
    assert_lossless(chunks, text)


@pytest.mark.parametrize("text", ["Long text " * 1200, "x" * 9000, "A paragraph.\n\n" * 500, "Tiny"])
def test_no_structure_uses_lossless_paragraph_packing(text):
    text = normalize(text)
    chunks = chunk_contract("demo", text)
    assert chunks[0].chunk_id.startswith("demo::para-1")
    assert all(chunk.method == "paragraph" for chunk in chunks)
    assert_lossless(chunks, text)


def test_empty_contract():
    assert chunk_contract("demo", normalize(" \nSource: SEC\n12")) == []


def test_load_contracts_normalizes_and_sorts(tmp_path):
    (tmp_path / "b.txt").write_text("B   text")
    (tmp_path / "a.txt").write_text("A\ttext")
    (tmp_path / "ignored.json").write_text("{}")
    assert load_contracts(tmp_path) == {"a": "A text\n", "b": "B text\n"}
    assert len(build_chunks(tmp_path)) == 2


def entry(title, size=9000):
    return {"title": title, "paragraphs": [{"context": "x" * size}]}


def test_selection_is_deterministic_round_robin_and_filters_lengths():
    entries = [entry("B-TYPE A"), entry("A-TYPE A"), entry("C-TYPE B"), entry("D-TINY", 100), entry("E-HUGE", 120001)]
    expected = ["A-TYPE A", "C-TYPE B", "B-TYPE A"]
    assert [e["title"] for e in download_cuad.select(entries, 10)] == expected
    assert download_cuad.select(entries, 2) == download_cuad.select(list(reversed(entries)), 2)
    assert download_cuad.select([], 25) == []


def test_safe_id_and_contract_type():
    assert download_cuad.safe_id(" Acme / Inc.-Contract ") == "Acme_Inc_Contract"
    assert len(download_cuad.safe_id("a" * 100)) == 90
    assert download_cuad.contract_type("Company-10.1_Supply Agreement") == "SUPPLY AGREEMENT"


def test_cached_archive_read_without_network(tmp_path, monkeypatch):
    dataset = {"data": [entry("A-TYPE")]}
    with zipfile.ZipFile(tmp_path / "data.zip", "w") as archive:
        archive.writestr("CUADv1.json", json.dumps(dataset))
    monkeypatch.setattr(download_cuad, "RAW_DIR", tmp_path)
    monkeypatch.setattr(download_cuad.urllib.request, "urlopen", lambda *_: pytest.fail("Cached archive must not redownload"))
    assert download_cuad.fetch_cuad_json() == dataset["data"]


def test_corrupt_archive_fails_loudly(tmp_path, monkeypatch):
    (tmp_path / "data.zip").write_bytes(b"invalid archive")
    monkeypatch.setattr(download_cuad, "RAW_DIR", tmp_path)
    with pytest.raises(zipfile.BadZipFile):
        download_cuad.fetch_cuad_json()


def test_user_supplied_scripts_are_byte_unchanged():
    expected = {
        "contract_qa/ingest.py": "3e43087cbf02dc77dc8e6a9dda43efa51cc5a373a404faacc13bef635af35e3e",
        "scripts/download_cuad.py": "efb01e29be2e5e2aa087ad400ea856515b1e73fc9313d2308ae85dae6c21f786",
    }
    for filename, checksum in expected.items():
        assert hashlib.sha256((ROOT / filename).read_bytes()).hexdigest() == checksum


def test_real_contracts_exact_slices_and_complete_nonwhitespace_coverage():
    manifest = json.loads((ROOT / "data/contracts/manifest.json").read_text())
    committed = [json.loads(line) for line in (ROOT / "data/chunks.jsonl").read_text().splitlines()]
    assert len(manifest) == 25
    assert len({contract["contract_id"] for contract in manifest}) == 25
    normalized = load_contracts(ROOT / "data/contracts")
    assert set(normalized) == {contract["contract_id"] for contract in manifest}
    regenerated = []
    for contract_id, text in normalized.items():
        chunks = chunk_contract(contract_id, text)
        assert_lossless(chunks, text)
        assert all(chunk.contract_id == contract_id for chunk in chunks)
        regenerated.extend(asdict(chunk) for chunk in chunks)
    assert regenerated == committed
    assert len({chunk["chunk_id"] for chunk in committed}) == len(committed)


def test_flattened_real_filing_recovers_38_headings_from_four_paragraph_starts():
    from contract_qa.ingest import _candidates

    text = load_contracts()["ABILITYINC_06_15_2020_EX_4_25_SERVICES_AGREEMENT"]
    assert sum(trusted for _, trusted in _candidates(text)) == 4
    assert len(find_headings(text)) == 38


@pytest.mark.xfail(strict=True, reason="Unchanged supplied _merge_heading_only loses a carried short final span because its copied dict fails an identity check")
def test_original_edge_case_preserves_consecutive_short_headings_at_eof():
    text = normalize("1. FIRST\n\n2. SECOND\n\n3. THIRD")
    assert_lossless(chunk_contract("short", text), text)


def test_ingestion_statistics_are_reproducible():
    from scripts.inspect_ingest import build_stats

    assert build_stats() == json.loads((ROOT / "data/ingest_stats.json").read_text())
