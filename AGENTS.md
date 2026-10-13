CONSTRAINTS
- Python 3.11+. No LangChain, LlamaIndex, FAISS, vector databases, or
  orchestration frameworks. Code must be short and readable enough for me to
  explain every line.
- OpenAI API: text-embedding-3-small for embeddings. For generation, list the
  models available to the key and pick two: the cheapest current chat model
  and the strongest current chat model. Record both in DECISIONS.md.
- Exact NumPy cosine search. 1,216 chunks don't justify an index.
- Never print, log, or commit API keys.
- Total API spend cap: $5. Cache embeddings to disk and reuse them; never
  re-embed unchanged chunks.
- pytest tests for everything deterministic.

DATA
- 25 contracts from CUAD v1 (The Atticus Project, CC BY 4.0), source
  https://github.com/TheAtticusProject/cuad (data.zip -> CUADv1.json).
- CUADv1.json is SQuAD format: each contract has 41 questions, one per clause
  category, with lawyer-annotated answer spans. An empty answer list means the
  contract lacks that clause; that is the refusal ground truth.

HOW INGEST.PY WORKS (do not modify it)
- normalize() collapses EDGAR spacing, drops page numbers and "Source:" lines.
- find_headings() trusts headings at paragraph start. Mid-line candidates
  (some filings flattened each page into one line) are kept only if they
  continue the numbering (after 4.1 accept 4.1.1, 4.2, 5, 5.1), rejecting
  cross-references like "pursuant to Section 6.1". "Article N" resets expected
  numbering to N, resyncing after a table of contents.
- chunk_contract(): one chunk per section; sections under 80 chars merge
  forward; over 4,000 chars split at paragraph breaks ("#p2" ids); duplicate
  ids get "~2"; no structure -> paragraph packing fallback.
- INVARIANT: chunk text == normalized_contract[char_start:char_end].
  Quote verification depends on it.

PHASES (one Codex task and one PR each, in order)
1. tests/test_ingest.py: normalize (space collapse, noise lines dropped,
   idempotent); is_successor truth table; find_headings (paragraph-start,
   wrapped "30 days" rejected, flattened sequence recovered, cross-reference
   rejected, Article resync); chunk_contract (slice invariant, unique ids,
   max 4,000 chars, heading-only merge, fallback); integration test on real
   data checking chunks cover all non-whitespace text.
2. contract_qa/retrieve.py: embed chunks in batches of 100, save
   data/embeddings.npy and data/ids.json. search(question, k=5,
   contract_id=None) returns top-k chunks with scores, optionally filtered to
   one contract. Unit-test cosine/top-k with small hand-made vectors.
3. contract_qa/answer.py: answer(question, contract_id=None, model=...) sends
   the 5 retrieved chunks with chunk_ids, temperature 0, and requires JSON
   {"answer": str, "citations": [{"chunk_id": str, "quote": str}]} or
   {"refusal": str}. System prompt: answer only from the provided clauses,
   quote verbatim, refuse if they don't answer the question. Verify each quote
   is a substring of its chunk after lowercasing and collapsing whitespace;
   any failed quote turns the whole response into a refusal. Add a CLI:
   python -m contract_qa.answer "question" [--contract ID]. Unit-test the
   verifier: exact match, whitespace difference, fabricated quote, wrong
   chunk_id, malformed JSON.
4. scripts/build_eval.py -> data/eval.jsonl: 25 contracts x 5 categories =
   125 items, scoped to one contract each, with these questions:
   - Governing Law: "Which jurisdiction's law governs this agreement?"
   - Termination For Convenience: "Can a party terminate this agreement
     without cause, and if so, how?"
   - Non-Compete: "Does this agreement restrict any party from competing?"
   - Exclusivity: "Does this agreement grant any exclusive rights?"
   - Cap On Liability: "Does this agreement cap either party's liability?"
   Store the annotated answer texts; expect_refusal = no annotations.
   scripts/run_eval.py --model NAME, retrieval filtered to the item's
   contract, matching by normalized text (not answer_start; CUAD offsets are
   raw text). Metrics:
   - Recall@5: share of answerable items where any top-5 chunk contains an
     annotated answer text.
   - Refusal accuracy: share of expect_refusal items the tool refused.
   - Grounded answer rate: share of answerable items answered (not refused)
     with verified citations, at least one citing a chunk that contains an
     annotated answer.
   - False refusal rate: share of answerable items refused.
   - Cost in dollars.
   Save results/<model>.json and results/summary.md (table, both models).
   Do not tune prompts or k against these results. Report them as measured,
   good or bad.
5. README.md: what it does and why (one paragraph), example CLI run with real
   output, data source and license, setup and run steps, results table copied
   from results/summary.md, design notes (why NumPy over FAISS, the
   flattened-filing fix, why quotes are verified in code, known limitations
   such as tables of contents and lettered sections).

PR RULES
- Each PR description: plain-language explanation of what was built and why,
  and the pytest summary line.
- Merge (squash) only after CI passes. If CI fails, fix and retry. After 3
  failed attempts on the same problem, choose the simplest working
  alternative that keeps the constraints and record why in DECISIONS.md.
- Never break the constraints to get unstuck.

FINISH
1. Write EXPLAIN.md for interview prep: for each module, what it does, why it's
   built that way, and the tradeoff behind it in plain language. Then 15 likely
   interview questions with short answers, including: why verify quotes in
   code, why empty CUAD answers make a refusal test set, why exact search at
   this scale, how the numbering-sequence check works, what the results show
   and what you'd improve next.
2. Run the full pipeline once from a fresh clone following the README and
   confirm it works.
3. Send me one message with: repo link, the results table, anything recorded
   in DECISIONS.md, and these resume bullets with brackets filled from
   results/summary.md:

Contract QA Tool | Python, NumPy, OpenAI API, pytest
- Built a contract question-answering tool over 25 commercial agreements from
  CUAD (The Atticus Project) that answers only from the source contracts, cites
  the exact clause it relied on, and refuses when no clause supports an answer
- Verified every citation in code by matching the quoted text against the
  source clause, converting any unverifiable answer into a refusal
- Built a 125-question evaluation set from CUAD's lawyer annotations, including
  questions about clauses the contracts lack, and compared [model A] and
  [model B] on retrieval (Recall@5 of [X]%), grounded answers ([X]% vs [Y]%),
  and correct refusals ([X]% vs [Y]%)
- Found that flattened SEC filings broke section detection (4 of 38 sections
  found in one contract) and fixed it with a numbering-sequence check, cutting
  median chunk size from 1,640 to 555 characters
- Used exact NumPy similarity search instead of a vector database, since 1,216
  clause-level chunks didn't justify the added complexity
