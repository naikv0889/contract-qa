"""Reproduce ingestion statistics and a paragraph-only heading ablation.

The ablation temporarily changes heading detection in memory. The supplied
source files, selected contracts, and committed production chunks stay unchanged.
Run: python scripts/inspect_ingest.py
"""

import hashlib
import json
from pathlib import Path
import statistics
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from contract_qa import ingest


def summarize(chunks: list) -> dict:
    sizes = [len(chunk.text) for chunk in chunks]
    return {
        "chunks": len(chunks),
        "median_chars": statistics.median(sizes),
        "max_chars": max(sizes),
        "total_chunk_chars": sum(sizes),
    }


def paragraph_headings(text: str) -> list:
    return [heading for heading, trusted in ingest._candidates(text) if trusted]


def build_stats() -> dict:
    contracts = ingest.load_contracts()
    production = ingest.build_chunks()
    heading_counts = {
        contract_id: {
            "paragraph_start": len(paragraph_headings(text)),
            "sequence_aware": len(ingest.find_headings(text)),
        }
        for contract_id, text in contracts.items()
    }
    with patch.object(ingest, "find_headings", side_effect=paragraph_headings):
        baseline = ingest.build_chunks()
    return {
        "contracts": len(contracts),
        "methodology": "Same selected contracts, normalization, and chunking. The paragraph-only ablation temporarily replaces find_headings with trusted paragraph-start candidates; source files and production chunks are unchanged. This is a newly measured ablation, not a historical benchmark.",
        "production": summarize(production),
        "paragraph_only_ablation": summarize(baseline),
        "heading_counts": heading_counts,
        "original_script_sha256": {
            filename: hashlib.sha256((ROOT / filename).read_bytes()).hexdigest()
            for filename in ("contract_qa/ingest.py", "scripts/download_cuad.py")
        },
        "source_archive_sha256": "f8161d18bea4e9c05e78fa6dda61c19c846fb8087ea969c172753bc2f45b999a",
        "source_json_sha256": "ed0b77d85bdf4014d7495800e8e4a70565b48ee6f8a2e5dca9cf8655dbf10eae",
    }


def main() -> None:
    stats = build_stats()
    path = ROOT / "data/ingest_stats.json"
    path.write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: stats[key] for key in ("contracts", "production", "paragraph_only_ablation")}, indent=2))


if __name__ == "__main__":
    main()
