"""Phase 1: load contracts and split them into section-level chunks.

Pipeline:  raw .txt  ->  normalize()  ->  find_headings()  ->  chunk_contract()

Every chunk is an exact slice of the normalized contract text, so later phases
can verify that a cited quote really appears in the contract.

Run:  python -m contract_qa.ingest      (writes data/chunks.jsonl)
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTRACTS_DIR = ROOT / "data" / "contracts"
CHUNKS_PATH = ROOT / "data" / "chunks.jsonl"

MAX_CHARS = 4000        # longer sections get split at paragraph breaks (~1k tokens)
MIN_SPAN_CHARS = 80     # shorter sections ('5. TERMINATION') merge into the next chunk
FALLBACK_TARGET = 1500  # paragraph packing size when no section structure is found
MIN_HEADINGS = 3        # fewer detected headings than this -> use the fallback


@dataclass
class Chunk:
    chunk_id: str         # "<contract_id>::<section_id>" (+ "#p2" for split parts)
    contract_id: str
    section_id: str       # "7.2", "Article IV", "preamble", "para-12"
    heading: str          # first line of the section, trimmed
    parent_heading: str   # enclosing top-level section / article heading, or ""
    text: str             # exact slice: normalized_text[char_start:char_end]
    char_start: int
    char_end: int
    method: str           # "section" or "paragraph" (fallback)


# ---------------------------------------------------------------- normalize

_NOISE_LINE = re.compile(
    r"""^(
        Source:\s.*                 # EDGAR footer: 'Source: ACME CORP, 8-K, 9/9/1999'
      | \d{1,3}                     # bare page number
      | -\s*\d{1,3}\s*-             # '- 7 -'
      | (?i:page\s+\d+(\s+of\s+\d+)?)
    )$""",
    re.VERBOSE,
)


def normalize(raw: str) -> str:
    """Clean EDGAR layout noise while keeping paragraph structure.

    - unify line endings, tabs and non-breaking spaces
    - collapse runs of spaces (EDGAR uses them for column alignment)
    - drop page numbers and 'Source:' footer lines
    - collapse 3+ newlines to a single blank line
    """
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\t", " ").replace("\xa0", " ")
    lines = []
    for line in text.split("\n"):
        line = re.sub(r" {2,}", " ", line).strip()
        if _NOISE_LINE.match(line):
            continue
        lines.append(line)
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


# ---------------------------------------------------------------- headings

# 'ARTICLE IV', 'Article 4'
_ARTICLE = re.compile(r"^(?:ARTICLE|Article)\s+([IVXLC]+|\d{1,2})\b")
# 'Section 7.2', 'SECTION 7.'
_SECTION = re.compile(r"^(?:SECTION|Section)\s+(\d{1,2}(?:\.\d{1,2}){0,2})\.?(?=\s|$)")
# '7.', '7.2', '7.2.1', '7.2.' followed by a capitalized word or quote.
# The capital-letter lookahead filters out wrapped prose like '30 days ...'.
_NUMBERED = re.compile(r"^(\d{1,2}\.(?:\d{1,2}\.?){0,2}|\d{1,2}(?:\.\d{1,2}){1,2})\s+(?=[A-Z\"“(])")


@dataclass
class Heading:
    start: int       # char offset of the heading line in normalized text
    section_id: str
    level: int       # 0 = article, 1 = '7.', 2 = '7.2', 3 = '7.2.1'
    line: str


def _classify(line: str) -> tuple[str, int] | None:
    if m := _ARTICLE.match(line):
        return f"Article {m.group(1)}", 0
    if m := _SECTION.match(line):
        num = m.group(1).rstrip(".")
        return num, num.count(".") + 1
    if m := _NUMBERED.match(line):
        num = m.group(1).rstrip(".")
        return num, num.count(".") + 1
    return None


# Mid-line candidates, for filings where whole pages were flattened into one
# line. Not preceded by cross-reference words ('Section 4.2', 'Sections 6.1').
_INLINE = re.compile(
    r"(?<=\s)"
    r"(ARTICLE\s+(?:[IVXLC]+|\d{1,2})\b"
    r"|Section\s+\d{1,2}(?:\.\d{1,2}){1,2}\.?(?=\s+[A-Z])"
    r"|\d{1,2}\.(?:\d{1,2}\.?){0,2}(?=\s+[A-Z\"“])"
    r"|\d{1,2}(?:\.\d{1,2}){1,2}(?=\s+[A-Z\"“]))"
)
_XREF_BEFORE = re.compile(r"(?i)(section|sections|article|clause|paragraph|exhibit|schedule|and|or|to|of)\s*$")

_ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


def _roman_to_int(s: str) -> int:
    total = 0
    for a, b in zip(s, s[1:] + " "):
        v = _ROMAN[a]
        total += -v if b != " " and _ROMAN[b] > v else v
    return total


def _num_tuple(section_id: str) -> tuple[int, ...] | None:
    if section_id.startswith("Article"):
        return None
    return tuple(int(p) for p in section_id.split("."))


def _article_num(section_id: str) -> int:
    n = section_id.split()[1]
    return int(n) if n.isdigit() else _roman_to_int(n)


def is_successor(prev: tuple[int, ...] | None, cand: tuple[int, ...]) -> bool:
    """Is `cand` a plausible next section number after `prev`?

    After 4.1 the plausible next numbers are 4.1.1 (first child), 4.2
    (sibling), or 5 / 5.1 (next top-level). Same idea at every depth.
    """
    if prev is None:
        return cand[0] <= 2 and all(p == 1 for p in cand[1:])
    if len(cand) == len(prev) + 1 and cand[:-1] == prev and cand[-1] == 1:
        return True  # first child
    for depth in range(len(prev)):
        bumped = prev[:depth] + (prev[depth] + 1,)
        if cand == bumped or (len(cand) == depth + 2 and cand[:-1] == bumped and cand[-1] == 1):
            return True  # sibling at this depth, optionally with its first child
    return False


def _candidates(text: str) -> list[tuple[Heading, bool]]:
    """All heading candidates as (heading, trusted). Trusted = starts a
    paragraph; untrusted = found mid-line and must pass the sequence check."""
    found: dict[int, tuple[Heading, bool]] = {}
    pos, prev_blank = 0, True
    for line in text.split("\n"):
        if line and prev_blank and (hit := _classify(line)):
            found[pos] = (Heading(pos, hit[0], hit[1], line), True)
        prev_blank = line == ""
        pos += len(line) + 1
    for m in _INLINE.finditer(text):
        if m.start() in found or _XREF_BEFORE.search(text[max(0, m.start() - 12):m.start()]):
            continue
        line = text[m.start():].split("\n", 1)[0]
        if hit := _classify(line):
            found[m.start()] = (Heading(m.start(), hit[0], hit[1], line), False)
    return [found[k] for k in sorted(found)]


def find_headings(text: str) -> list[Heading]:
    """Return section headings in document order.

    Headings that start a paragraph are trusted. Requiring a paragraph start
    avoids false hits on wrapped lines that happen to begin with a number.
    Mid-line candidates are kept only if they continue the numbering sequence,
    which filters out cross-references, dollar amounts, and dates.
    """
    headings: list[Heading] = []
    last_num: tuple[int, ...] | None = None
    last_article = 0
    for h, trusted in _candidates(text):
        num = _num_tuple(h.section_id)
        if not trusted:
            ok = (_article_num(h.section_id) == last_article + 1) if num is None \
                else is_successor(last_num, num)
            if not ok:
                continue
        headings.append(h)
        if num is None:
            # 'Article 5' means section numbering continues as 5.1, 5.2, ...
            # This also resyncs after a table of contents.
            last_article = _article_num(h.section_id)
            last_num = (last_article,)
        else:
            last_num = num
    return headings


# ---------------------------------------------------------------- chunking

def _trim(text: str, start: int, end: int) -> tuple[int, int]:
    """Shrink [start, end) to exclude surrounding whitespace."""
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _split_long(text: str, start: int, end: int, limit: int) -> list[tuple[int, int]]:
    """Split [start, end) into pieces <= limit chars, preferring paragraph
    breaks, then sentence ends, then a hard cut."""
    pieces = []
    while end - start > limit:
        window = text[start:start + limit]
        cut = window.rfind("\n\n")
        if cut < limit // 3:
            cut = window.rfind(". ") + 1 if window.rfind(". ") > limit // 3 else limit
        pieces.append(_trim(text, start, start + cut))
        start = start + cut
    pieces.append(_trim(text, start, end))
    return [p for p in pieces if p[1] > p[0]]


def _short(line: str, n: int = 100) -> str:
    return line if len(line) <= n else line[: n - 1].rstrip() + "…"


def _sections(text: str, headings: list[Heading]) -> list[dict]:
    """Turn headings into contiguous spans, with a preamble before the first."""
    spans = []
    first = headings[0].start
    if text[:first].strip():
        spans.append(dict(start=0, end=first, section_id="preamble",
                          heading="", parent=""))
    parent = ""
    for i, h in enumerate(headings):
        end = headings[i + 1].start if i + 1 < len(headings) else len(text)
        if h.level <= 1:
            parent = ""          # top-level headings have no parent
        spans.append(dict(start=h.start, end=end, section_id=h.section_id,
                          heading=_short(h.line), parent=parent))
        if h.level <= 1:
            parent = _short(h.line)
    return spans


def _merge_heading_only(text: str, spans: list[dict]) -> list[dict]:
    """A span like '5. TERMINATION' with no body text gets glued onto the
    following span so we never embed a chunk that is just a title."""
    merged: list[dict] = []
    carry_start = None
    for s in spans:
        if carry_start is not None:
            s = {**s, "start": carry_start}
            carry_start = None
        span_len = len(text[s["start"]:s["end"]].strip())
        if s["section_id"] != "preamble" and span_len < MIN_SPAN_CHARS and s is not spans[-1]:
            carry_start = s["start"]
            continue
        merged.append(s)
    return merged


def _paragraph_spans(text: str) -> list[dict]:
    """Fallback: pack whole paragraphs into ~FALLBACK_TARGET-char spans."""
    paras = [(m.start(), m.end()) for m in re.finditer(r"[^\n](?:.|\n(?!\n))*", text)]
    spans: list[dict] = []
    cur_start = None
    first_idx = 0
    for idx, (ps, pe) in enumerate(paras, start=1):
        if cur_start is None:
            cur_start, first_idx = ps, idx
        if pe - cur_start >= FALLBACK_TARGET or idx == len(paras):
            spans.append(dict(start=cur_start, end=pe, section_id=f"para-{first_idx}",
                              heading=_short(text[cur_start:pe].split("\n", 1)[0]),
                              parent=""))
            cur_start = None
    return spans


def chunk_contract(contract_id: str, text: str) -> list[Chunk]:
    """Chunk one normalized contract. Section-based when structure is found,
    paragraph-based otherwise."""
    headings = find_headings(text)
    if len(headings) >= MIN_HEADINGS:
        spans, method = _merge_heading_only(text, _sections(text, headings)), "section"
    else:
        spans, method = _paragraph_spans(text), "paragraph"

    chunks: list[Chunk] = []
    seen: dict[str, int] = {}
    for s in spans:
        pieces = _split_long(text, *_trim(text, s["start"], s["end"]), MAX_CHARS)
        base = f"{contract_id}::{s['section_id']}"
        # numbering can restart in exhibits/schedules -> keep ids unique
        seen[base] = seen.get(base, 0) + 1
        if seen[base] > 1:
            base = f"{base}~{seen[base]}"
        for n, (a, b) in enumerate(pieces, start=1):
            chunks.append(Chunk(
                chunk_id=base if len(pieces) == 1 else f"{base}#p{n}",
                contract_id=contract_id,
                section_id=s["section_id"],
                heading=s["heading"],
                parent_heading=s["parent"],
                text=text[a:b],
                char_start=a,
                char_end=b,
                method=method,
            ))
    return chunks


# ---------------------------------------------------------------- I/O

def load_contracts(directory: Path = CONTRACTS_DIR) -> dict[str, str]:
    """{contract_id: normalized text} for every .txt in the directory."""
    return {p.stem: normalize(p.read_text(encoding="utf-8"))
            for p in sorted(directory.glob("*.txt"))}


def build_chunks(directory: Path = CONTRACTS_DIR) -> list[Chunk]:
    chunks = []
    for cid, text in load_contracts(directory).items():
        chunks.extend(chunk_contract(cid, text))
    return chunks


def main() -> None:
    chunks = build_chunks()
    with CHUNKS_PATH.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")
    n_contracts = len({c.contract_id for c in chunks})
    print(f"{len(chunks)} chunks from {n_contracts} contracts -> {CHUNKS_PATH}")


if __name__ == "__main__":
    main()
