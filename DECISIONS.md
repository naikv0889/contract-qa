# Decisions and deviations

## Scope and integrity

- The original `ingest.py` and `download_cuad.py` arrived after initial
  reconstruction work. The final repository uses the supplied scripts unchanged;
  generated data and tests were rebuilt against them. Reconstructed versions
  are not part of the final implementation. Original file hashes are recorded
  in `VALIDATION.md`.
- The requested saved cloud environment was not available. Work proceeded in
  the available cloud workspace after that limitation and workaround were
  discussed. The user's computer was not accessed.
- `OPENAI_API_KEY` is absent. No model listing, paid embedding, live answer, or
  two-model benchmark has run. API spend during construction is $0. Model
  choices remain pending a real key, an available-model listing, official
  pricing verification, and a capability check for the required chat options.
- GitHub publication is complete in the public
  [naikv0889/contract-qa repository](https://github.com/naikv0889/contract-qa).
  Phases 1–5 each passed remote CI and were squash merged through PRs
  [#1](https://github.com/naikv0889/contract-qa/pull/1),
  [#2](https://github.com/naikv0889/contract-qa/pull/2),
  [#3](https://github.com/naikv0889/contract-qa/pull/3), and
  [#4](https://github.com/naikv0889/contract-qa/pull/4), and
  [#5](https://github.com/naikv0889/contract-qa/pull/5).
  A documentation-only follow-up records final validation evidence.
  Public commits use clean source snapshots without private project background.
- No unsupported resume metrics are filled in. The original historical claims
  of a 1,640-to-555-character median reduction are not reproduced before/after
  measurements and must not be claimed as measured. See the measured ablation below.

## Simplest reproducible choices

- Use the supplied downloader's deterministic selection, including its
  contract-type round-robin and length filters. Preserve a source mapping for
  evaluation rather than assuming a source-order sample.
- Python 3.11+ and only the four requested third-party dependencies. SQLite
  for the durable budget ledger is from Python's standard library; retrieval
  is exact NumPy cosine search, with no database/vector framework.
- Cache embeddings by content and embedding model, so changing IDs does not
  require paying to embed identical text again. Persist cache entries as soon
  as a successful batch returns.
- Refuse malformed outputs, empty evidence, unknown chunks, and invented
  quotes. Quote verification establishes textual provenance, not that the
  answer logically follows from the quote or gives correct legal advice.
- Missing CUAD answers are the requested refusal ground truth for this
  benchmark. They do not prove every possible contract interpretation lacks
  an answer; the task is bounded by this annotation set.
- Keep evaluation questions, prompt, and k=5 fixed. Report bad measurements
  honestly rather than tune on this small evaluation set.
- Paid calls require explicit verified pricing configuration. Reserve a
  conservative upper bound before each request, disable automatic retries,
  reconcile observed usage, and retain uncertain charges after failed calls.
  Never reset the ledger to bypass the $10 cap.

## Remaining verification

The local deterministic pipeline, source counts, chunk statistics, test
summary, and fresh-clone checks are recorded in `VALIDATION.md`. Live API
results and publication checks are separate gates. Verified
remote CI results are recorded below; missing live model results remain unmeasured.

## Generation API shape

- Use Chat Completions JSON mode plus exact in-code schema validation. The
  requested answer-or-refusal root union is not compatible with strict
  Structured Outputs' root-schema requirements. See the official
  [supported schemas](https://developers.openai.com/api/docs/guides/structured-outputs#supported-schemas).
  Require explicit verification that selected models support JSON mode and
  temperature zero; do not silently drop requested options.

## Original ingestion audit

- The supplied scripts produce exactly 1,216 chunks from 25 contracts. Median
  chunk length is 555 characters and maximum is 3,993. All non-whitespace
  normalized source text is covered for the selected dataset.
- The ABILITY filing has 4 paragraph-start headings and 38 after sequence-aware
  recovery. This specific claim is reproduced. A new paragraph-only ablation
  over all 25 contracts gives median 854 characters, not the historical 1,640.
  Use the measured 854-to-555 comparison or omit the baseline; do not claim the
  unverified historical value.
- The unchanged supplied ingestion script has a synthetic edge case: a series
  of short heading-only sections at end-of-file can be lost. A strict expected
  failure exposes it; ordinary dataset coverage tests pass. Preserving the
  user's original scripts takes precedence over silently patching this bug.
  Future general-purpose ingestion should fix it with explicit permission.

## UI addition

- The later request for an intuitive, smooth, aesthetic interface is implemented
  with a localhost Python standard-library server and vanilla HTML/CSS/JS.
  This retains the original dependency constraints and CLI. No hosted backend,
  frontend framework, or API key in browser code is needed.

## Conservative API reservations

- Full-window chat reservation may block an expensive model even when a short
  prompt would cost less. This is a known safety/usability tradeoff. Do not
  shrink the verified upper bound to make the request fit the cap. Price inputs
  must cover the highest applicable context-tier rates.
- `CONTRACT_QA_BUDGET_PATH` can point all clones to one absolute ledger. A copied
  repository does not carry spend history by default; the global budget is only
  protected when every paid run shares the same persistent ledger.

## Browser verification boundary

- HTTP/API and static-asset tests passed, but this execution environment did
  not permit a rendered browser QA session against the localhost app. A
  headless browser launch failed on a restricted local socket; a supported
  cloud-browser attempt could not reach the isolated localhost server. This
  limitation is reported, not hidden behind simulated screenshots.
