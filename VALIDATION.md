# Validation record

## Reproduced data and provenance

- CUAD: 25 deterministic contracts selected by the supplied downloader
- Production chunks: **1,216**, median **555** characters, maximum **3,993**
- Evaluation: **125** items, **65** answerable and **60** absent-clause
- All 65 answerable items have an annotated span contained in at least one
  scoped corpus chunk. This is corpus consistency, **not Recall@5**.
- Every selected contract passes exact normalized slice offsets, unique IDs,
  maximum-length, and complete non-whitespace coverage checks.
- ABILITY filing: 4 trusted paragraph-start headings versus 38 with sequence
  recovery. All-contract paragraph-only ablation median: 854 characters.

Original file SHA256 values, verified unchanged:

- `contract_qa/ingest.py`: `3e43087cbf02dc77dc8e6a9dda43efa51cc5a373a404faacc13bef635af35e3e`
- `scripts/download_cuad.py`: `efb01e29be2e5e2aa087ad400ea856515b1e73fc9313d2308ae85dae6c21f786`

Official archive SHA256:
`f8161d18bea4e9c05e78fa6dda61c19c846fb8087ea969c172753bc2f45b999a`

Raw CUADv1.json SHA256:
`ed0b77d85bdf4014d7495800e8e4a70565b48ee6f8a2e5dca9cf8655dbf10eae`

Run `python scripts/inspect_ingest.py` to reproduce the ingestion audit.

## Test interpretation

Tests use deterministic synthetic vectors, fake API clients, local HTTP
requests, and real committed contract data. No test needs an API key. A strict
expected failure documents the supplied ingestion script's trailing-short-
heading edge case. This is not silently counted as passing behavior. The actual
selected dataset's coverage tests pass normally.

The execution environment uses Python 3.12; the workflow targets Python 3.11.
Remote CI status must be checked separately and is not inferred from local tests.

## Paid pipeline

No API key is available. Model listing, live embeddings, live generated answers,
and both model evaluations have not run. Spend incurred during construction:
**$0**. The offline demo is a real clause passed directly to the verifier, clearly
labeled as a demonstration rather than generated model output.

## Current deterministic run

- Full suite: **204 passed, 1 xfailed in 16.15s** on Python 3.12
- JavaScript syntax: `node --check contract_qa/static/app.js` passed
- Python byte compilation: `python -m compileall -q contract_qa scripts` passed
- Git whitespace check: `git diff --check` passed
- Local HTTP tests exercised real assets and endpoints plus configured,
  unconfigured, answer, refusal, malformed, cross-origin, and concurrency states
- Browser visual QA was attempted but is **not verified**: the isolated
  executor's localhost server was not reachable by the cloud browser, and
  headless Chromium launch was blocked by local socket restrictions. The cloud
  browser also disallowed file URLs. No screenshot or responsive-rendering
  success is claimed. Responsive CSS and semantic/keyboard behavior are
  implemented; they still need a normal browser check on the user's machine.

## Fresh-clone offline reproduction

A new local clone of the release source was tested in a clean virtual
environment with dependencies freshly installed from `requirements.txt`:

1. `python -m pytest -q` → **204 passed, 1 xfailed in 16.15s**
2. `python -m contract_qa.ingest` → **1,216 chunks from 25 contracts**
3. `python scripts/download_cuad.py` downloaded the official archive anew;
   its checksum matched the recorded source
4. `python scripts/build_eval.py` read the ZIP-only cache and rebuilt **125
   items (65 answerable, 60 absent-clause)**
5. `python scripts/inspect_ingest.py` reproduced the statistics
6. `python scripts/demo_offline.py` accepted the real annotated quotation and
   refused an invented quotation
7. `git diff --exit-code -- data` passed: regenerated committed data was
   byte-for-byte identical
8. Python compilation passed

The clean environment installed NumPy 2.5.4, OpenAI 2.54.0,
python-dotenv 1.2.4, and pytest 9.1.1. This validates the offline pipeline from
a **local clone**, not a public GitHub fresh clone or the unavailable paid
pipeline. API calls and browser-rendering verification remain separate gates.

## Verified publication checkpoint

The repository is public at
[naikv0889/contract-qa](https://github.com/naikv0889/contract-qa).
Phases 1–5 each passed their GitHub Actions CI checks and were squash merged:

- [Phase 1: ingestion](https://github.com/naikv0889/contract-qa/pull/1)
- [Phase 2: retrieval](https://github.com/naikv0889/contract-qa/pull/2)
- [Phase 3: verified answers](https://github.com/naikv0889/contract-qa/pull/3)
- [Phase 4: evaluation](https://github.com/naikv0889/contract-qa/pull/4)
- [Phase 5: UI and documentation](https://github.com/naikv0889/contract-qa/pull/5)

The verified main commit after phase 5 is
`f3155cb5207ba95ebb1861aa6c03c70887c94a92`.
The [phase 5 CI run](https://github.com/naikv0889/contract-qa/actions/runs/38447578139)
reported **204 passed, 1 xfailed in 11.27s** on Python 3.11 before merge.
These are real remote CI results, separate from the local fresh-clone checks
above. Live API measurements and rendered-browser QA remain unverified.
The [post-merge main-branch CI run](https://github.com/naikv0889/contract-qa/actions/runs/38447715526)
also passed for that exact phase-5 merge commit.

## Public GitHub fresh-clone reproduction

After the five phase merges, a new clone was fetched directly from
`https://github.com/naikv0889/contract-qa.git`, with HEAD verified as
`f3155cb5207ba95ebb1861aa6c03c70887c94a92`.
A newly created virtual environment installed `requirements.txt` from scratch.
The README's offline pipeline completed successfully:

- Full tests: **204 passed, 1 xfailed in 15.58s** on Python 3.12
- Ingestion: **1,216 chunks from 25 contracts**
- Official source downloaded afresh; archive checksum matched the reference
- ZIP-backed evaluation rebuild: **125 items (65 answerable, 60 absent-clause)**
- Ingestion statistics and labeled offline quote demonstration reproduced
- `git diff --exit-code -- data` passed, confirming byte-identical generated data
- Python byte compilation passed and the fresh-clone worktree remained clean

No API key or paid request was used. This verifies public source distribution
and the offline pipeline; it does not turn unmeasured model quality or blocked
browser-rendering checks into completed tests.


## Published environment follow-up (2026-10-13)

This dated checkpoint supersedes the earlier missing-key and browser-launch
limitations. The key is present and authenticated model listing succeeded.
No paid API calls, embeddings, generated answers or evaluations ran; actual
spend and ledger reservations remain $0. Billing access is untested. The
current blocker is the model/temperature and reservation conflict documented
in DECISIONS.md, not missing credentials.

- Full local suite after lowering the cap: **206 passed, 1 xfailed in 10.29s**.
- The persistent ledger is `/workspace/contract-qa/data/budget.sqlite3`;
  `CONTRACT_QA_BUDGET_PATH` points every execution and clone there.
- Actual budget CLI: `Spent or conservatively reserved: $0.000000 / $5`.
- Actual answer CLI exits 2: `Verified pricing is required at data/pricing.json; see README.md for its schema.`
- Headless Chromium rendered the real localhost application at desktop
  1440×1000 and mobile 390×844. Real server checks passed: 25 contracts,
  longest contract selection, starter question, Ctrl+Enter, and configuration
  error display. No horizontal overflow or JavaScript errors occurred.
- Explicit browser response fixtures separately passed loading, disabled
  duplicate submission, expandable public-source quotations, refusal, 503
  errors, repeat submission and keyboard focus. These are rendering checks,
  **not live model or retrieval verification**. Fixture screenshots visibly
  label their answer as fixture-only. No real generated answer is claimed.
- Evidence: [browser checks](results/browser/checks.json),
  [desktop configuration error](results/browser/desktop-actual-config-error.png),
  [mobile configuration error](results/browser/mobile-actual-config-error.png),
  [desktop fixture quotes](results/browser/desktop-fixture-quotes.png),
  [mobile fixture quotes](results/browser/mobile-fixture-quotes.png).

Live answer/refusal UI integration remains unverified until the paid-model
constraint conflict is resolved. The overall project is not complete.

The cap change was published through draft [PR #7](https://github.com/naikv0889/contract-qa/pull/7), then squash merged after
[CI run 38451067354](https://github.com/naikv0889/contract-qa/actions/runs/38451067354)
succeeded for exact head `5f16a5caa8041565c5e13afb77e17354fdf71d0b`.
Merge commit: `5e69877594f2d49c548a735a31e864d313837d38`.

### Fresh public clone after the cap change

A new public clone at `5e69877594f2d49c548a735a31e864d313837d38` installed
requirements into a new Python 3.12 virtual environment. The complete README
offline pipeline passed: **206 passed, 1 xfailed in 10.27s**, 1,216 chunks,
a fresh official CUAD download with matching archive checksum, 125 evaluation
items (65 answerable / 60 absent), the ingestion audit, and the offline quote
demo. `git diff --exit-code -- data` proved byte-identical regeneration;
compilation passed and the clone stayed clean. Its budget command used the
same absolute ledger and reported **$0.000000 / $5**. No embedding cache was
created or copied and no paid API request was made.

## Approved comparison and generation-access blocker (2026-10-13)

This checkpoint supersedes the earlier model-selection pause. The user approved
Luna plus stronger compatible Sol, with the $5 total cap unchanged. Both model
IDs are visible to the key and exact Responses input counting succeeded.
A provider count of the frozen request replaces the full-window bound only
for the Responses path; generation uses identical input, JSON mode,
temperature 0, reasoning none and a maximum 1,024 output tokens.

- Full deterministic suite: **224 passed, 1 xfailed in 10.26s**.
- New tests cover invalid/oversized counts, client input mutation, count timeout,
  budget rejection before generation, incomplete outputs and cache-write costs.
- First live generation: **HTTP 401 AuthenticationError**, `gpt-6-luna`.
  No raw credential-bearing error was logged. No retry or stronger-model call
  followed, and no credential/security setting was changed.
- Persistent ledger: one unsettled reservation, **$0.000085125**; settled
  usage-confirmed spend **$0**. Actual rejected-request billing is unknown.
  The ledger was extended with cache usage details, never deleted or reset.
- No embeddings, benchmark items, or live UI answers were generated. The old
  localhost process was stopped after the authentication failure.
- Browser evidence from the earlier checkpoint remains valid for rendering,
  but live answer/refusal integration is still blocked.
- [Capability smoke record](results/model_smoke.json) and
  [verified rates](results/pricing-2026-10-13.json) preserve the latest evidence.

The conditional ceiling for two 125-question evaluations at the enforced
10,000 input / 1,024 output token limits is $4.647176 including initial embedding
bounds and worst-case cache-write input rates. Failed requests and smoke/UI
work consume the remaining allowance in the same ledger. This is not a measured
benchmark cost or permission to exceed $5.
