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
Phases 1–4 each passed their GitHub Actions CI checks and were squash merged:

- [Phase 1: ingestion](https://github.com/naikv0889/contract-qa/pull/1)
- [Phase 2: retrieval](https://github.com/naikv0889/contract-qa/pull/2)
- [Phase 3: verified answers](https://github.com/naikv0889/contract-qa/pull/3)
- [Phase 4: evaluation](https://github.com/naikv0889/contract-qa/pull/4)

The verified main commit after phase 4 is
`b72a363ee4500ea5f6cf84c33d2dd9973e61f287`.
Phase 5 is pending at this checkpoint; its current status is available in
[the repository's pull requests](https://github.com/naikv0889/contract-qa/pulls).
These are real remote CI results, separate from the local fresh-clone checks
above. Live API measurements and rendered-browser QA remain unverified.
