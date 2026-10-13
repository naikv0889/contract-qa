"""Download CUAD v1 from The Atticus Project's official GitHub repo and pick a
deterministic subset of contracts for this project.

Source: https://github.com/TheAtticusProject/cuad (data.zip -> CUADv1.json)
License: CC BY 4.0 (see README).

Usage:
    python scripts/download_cuad.py            # 25 contracts (default)
    python scripts/download_cuad.py --n 30

Writes:
    data/contracts/<contract_id>.txt   raw contract text, unmodified
    data/contracts/manifest.json       id, title, type, source, char length
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

CUAD_ZIP_URL = "https://raw.githubusercontent.com/TheAtticusProject/cuad/main/data.zip"
ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "contracts"
RAW_DIR = ROOT / "data" / "raw"

# Skip extremes: tiny filings (joint filing agreements are ~1 page) and
# 300k-character monsters that would dominate the index.
MIN_CHARS = 8_000
MAX_CHARS = 120_000


def fetch_cuad_json() -> list[dict]:
    """Return CUADv1.json's `data` list, caching the zip under data/raw/."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = RAW_DIR / "data.zip"
    if not zip_path.exists():
        print(f"Downloading {CUAD_ZIP_URL} ...")
        with urllib.request.urlopen(CUAD_ZIP_URL) as resp:
            zip_path.write_bytes(resp.read())
    sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    print(f"data.zip sha256={sha}")
    with zipfile.ZipFile(zip_path) as zf:
        with zf.open("CUADv1.json") as f:
            return json.load(io.TextIOWrapper(f, encoding="utf-8"))["data"]


def contract_type(title: str) -> str:
    """'LIMEENERGYCO_09_09_1999-EX-10-DISTRIBUTOR AGREEMENT' -> 'DISTRIBUTOR AGREEMENT'."""
    t = title.split("-")[-1].strip().upper()
    return re.sub(r"^[\d.]+_", "", t)  # drop exhibit prefixes like '10.1_'


def safe_id(title: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_")[:90]


def select(entries: list[dict], n: int) -> list[dict]:
    """Round-robin across contract types (alphabetical within each type) so the
    sample is varied and the same every run."""
    by_type: dict[str, list[dict]] = defaultdict(list)
    for e in sorted(entries, key=lambda e: e["title"]):
        length = len(e["paragraphs"][0]["context"])
        if MIN_CHARS <= length <= MAX_CHARS:
            by_type[contract_type(e["title"])].append(e)
    # most common types first, ties broken by name
    types = sorted(by_type, key=lambda t: (-len(by_type[t]), t))
    picked: list[dict] = []
    depth = 0
    while len(picked) < n:
        added = False
        for t in types:
            if depth < len(by_type[t]) and len(picked) < n:
                picked.append(by_type[t][depth])
                added = True
        if not added:
            break
        depth += 1
    return picked


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=25)
    args = ap.parse_args()

    entries = fetch_cuad_json()
    chosen = select(entries, args.n)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    for e in chosen:
        cid = safe_id(e["title"])
        text = e["paragraphs"][0]["context"]
        (OUT_DIR / f"{cid}.txt").write_text(text, encoding="utf-8")
        manifest.append({
            "contract_id": cid,
            "cuad_title": e["title"],
            "type": contract_type(e["title"]),
            "chars": len(text),
            "source": CUAD_ZIP_URL,
        })
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote {len(manifest)} contracts to {OUT_DIR}")


if __name__ == "__main__":
    main()
