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

The requested model-comparison bullet is not supported yet. The user approved
`gpt-6-luna` versus `gpt-6-sol` with temperature 0 and reasoning none. Both IDs
are visible and exact input counting works, but the first Luna generation
returned HTTP 401 AuthenticationError. All quality metrics remain unmeasured.
Use actual metrics only after two completed runs; do not replace N/A with zero.
The measured 854-to-555-character ablation is valid; the historical 1,640-character
baseline remains unverified.
