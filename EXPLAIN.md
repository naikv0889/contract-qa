# Interview preparation

## Modules and tradeoffs

### Download
`scripts/download_cuad.py` fetches the official CUAD archive and selects a
fixed set of 25 agreements using contract-type round-robin sampling and length
filters. Keeping the source title mapping and file hashes
lets another developer reproduce the dataset. The tradeoff is that a small
fixed sample is not representative of all commercial contracts.

### Ingestion
`contract_qa/ingest.py` normalizes filing noise, finds likely section headings,
and splits contracts into bounded chunks. Every chunk remains an exact slice
of the normalized contract, so offsets can be checked mechanically. Numbered
headings in the middle of flattened paragraphs need a plausible successor;
otherwise ordinary cross-references can look like sections. Long sections
split at paragraph breaks where possible. Hard splits are necessary when one
paragraph itself exceeds the limit. Heuristics remain imperfect for tables of
contents, lettered sections, and unusual SEC formatting.

### Retrieval
`contract_qa/retrieve.py` embeds text, reuses cached vectors, and computes every
cosine similarity with NumPy. A filter restricts evaluation to the specified
contract before selecting five chunks. Exact search is simple and cheap at
this scale. It becomes expensive for millions of chunks, where an approximate
index and a stronger storage design may be appropriate.

### Generation and evidence
`contract_qa/answer.py` asks a selected chat model to answer only from retrieved
chunks and return structured evidence. The response is accepted only when
every cited chunk was supplied and every normalized quote exists in that
chunk. The tradeoff is conservative refusal and an extra validation step.
Valid quotes alone cannot establish that an answer is legally correct.

### Budget
`contract_qa/budget.py` records reservations and measured charges persistently.
A call reserves money before sending; a successful usage report reconciles
the charge. Uncertain failures retain the reservation, preferring an early
stop over exceeding the cap. A conservative estimate may reject a request
that would ultimately have been cheap. Only verified, current pricing should
be configured. The ledger tracks this application, not unrelated account use.

### Evaluation
`scripts/build_eval.py` maps five clause categories to 125 scoped questions and
retains CUAD's annotated spans. `scripts/run_eval.py` retrieves once, measures
span recall, asks the model, and measures refusal and grounding independently.
It checks normalized text rather than raw character positions because
normalization changes offsets. The benchmark is small and not a substitute
for lawyer review or a held-out production evaluation.

### Browser workspace
`contract_qa/web.py` serves local static assets and three small API routes.
The API shares a retriever and budget, serializes paid calls, rejects foreign
origins, validates contract/model IDs before spending, and returns sanitized
errors. `contract_qa/static/` renders untrusted strings with textContent rather
than HTML, so contract/model text is not executed as markup. The tradeoff is a
single-user local prototype rather than an authenticated multi-user service.
The API key stays server-side. Missing configuration is visibly different from
a refused answer.

## Fifteen likely questions

1. **Why verify quotes in code?** Models can invent quotations. A substring
   check is cheap, repeatable, and does not require trusting a second model.
2. **Does a verified quote prove correctness?** No. The quote can be irrelevant,
   incomplete, or misinterpreted. We verify provenance and measure grounding
   separately, not legal correctness.
3. **Why use empty CUAD answers for refusal tests?** They supply an existing
   lawyer-annotated absence label for the selected clause categories, avoiding
   invented absence questions. Annotation limitations still apply.
4. **Why exact NumPy search?** There are only 25 agreements. A matrix product
   is easy to inspect and avoids operating an unnecessary vector database.
5. **How does the numbering check work?** A flattened mid-line candidate must
   plausibly follow the previous section, such as a child or next sibling.
   Article headings resynchronize the sequence. This rejects many references.
6. **Why retain offsets?** They prove each chunk matches its normalized source
   slice and make debugging missing or duplicated contract text easier.
7. **Why five retrieved chunks?** It is the fixed brief's baseline, balancing
   context length and coverage. We do not optimize k against reported results.
8. **What happens if the model returns malformed JSON?** The response becomes
   a refusal; malformed output must not slip through as an answer.
9. **What if one of several quotes is fabricated?** Reject the entire answer.
   Accepting only the good citations could hide unsupported claims.
10. **What does Recall@5 measure?** Among answerable questions, whether any of
    five retrieved chunks contains a complete annotated answer span.
11. **How does grounded answer rate differ?** It also requires a non-refusal,
    valid citations, and citation of a chunk containing an annotated answer.
12. **What is a false refusal?** Refusing a question with a nonempty annotated
    answer. This measures the cost of excessive conservatism.
13. **How is the budget protected?** Persistent reservations precede API calls,
    observed usage reconciles them, caching avoids repeat embeddings, and
    automatic SDK retries are disabled.
14. **What do the results show?** Consult the actual results table. The key now
    supports model listing/counting, but generation returned HTTP 401.
    Model quality is unmeasured; passing deterministic tests is
    evidence about code behavior, not evidence of model accuracy.
15. **What would you improve next?** Evaluate a larger held-out set, inspect
    retrieval failures and section boundaries, handle cross-clause context,
    and add entailment review with lawyers. Preserve the original baseline
    before trying reranking or different chunking.


The current model decision is an example of enforcing requirements before
spending: authenticated access is available, but Astra requires reasoning and
cannot accept temperature 0. Its conservative full-window reservation also
exceeds $5. Browser rendering now passes on desktop and mobile with explicitly
labeled fixtures; live answer quality and end-to-end paid behavior are still
unmeasured. See DECISIONS.md and VALIDATION.md for evidence and next options.


The approved compatible comparison now uses Luna and Sol, with the identical
prompt on Responses, temperature 0 and reasoning none. `counted.py` freezes
all input fields, obtains the provider's exact count including framing, rejects
requests above the priced 10,000-token limit, then reserves input plus the full
1,024-token output allowance. It never transfers a Responses count to Chat
Completions. The first live generation returned HTTP 401; its reservation is
retained, and no benchmark metrics or model-comparison resume claims exist.
