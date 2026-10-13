# Resume wording supported today

**Contract QA Tool | Python, NumPy, OpenAI API, pytest**

- Built a contract question-answering tool over 25 CUAD commercial agreements,
  with exact-clause citations, fail-closed quotation checks, and a responsive
  browser interface for inspecting answers and source evidence
- Verified every accepted citation in code by matching quoted text against
  retrieved source clauses, converting unverifiable model output into refusal
- Built a 125-question evaluation set from lawyer annotations, including 60
  absent-clause questions, with reproducible retrieval, grounding, refusal,
  and API-cost metrics
- Verified numbering-sequence recovery increased detected headings from 4 to
  38 in one flattened SEC filing; measured a median chunk length of 555
  characters versus 854 in a paragraph-only ablation
- Used exact NumPy cosine search over 1,216 clause-level chunks with persistent
  embedding caching and a conservative $5 API spending ledger

## Add only after live evaluation

The requested model-comparison bullet is not supported yet. Both models are
identified as candidates (`gpt-6-luna` and `gpt-6-astra`), but quality metrics
remain unmeasured: Astra cannot satisfy the required temperature 0, and its
full-window reservation exceeds the $5 cap. The key now authenticates.
Once two complete runs are available, use their actual model IDs,
Recall@5, grounded answer rates, and refusal accuracy from
`results/summary.md`. Do not replace N/A with zero or use a fabricated score.
The historical 1,640-character baseline is unverified and must not be claimed.
