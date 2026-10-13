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
- The initial workspace lacked an API key. In the published environment on
  2026-10-13, authenticated model listing succeeded. No paid requests have
  occurred. The current model/capability conflict is recorded below.
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
  Never reset the ledger to bypass the $5 cap.

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


## Published-environment model decision (2026-10-13)

- The user revised the total project cap to **$5**, superseding the initial
  budget. Code, tests and instructions enforce this before any paid calls.
  All executions use the same persistent ledger; never reset or copy it to
  create a new allowance. No embedding cache exists yet because no paid call ran.
- Safe authenticated model listing succeeded through the environment's normal
  API connection. Both `gpt-6-luna` and `gpt-6-astra` are visible to the key.
  Listing proves authentication/model visibility, not generation billing access.
- Interpret “current” as the current generation: **gpt-6-luna** is the cheapest
  current candidate and **gpt-6-astra** the strongest. The cheaper legacy
  `gpt-5-nano` ($0.05/$0.40 per million input/output tokens) is explicitly
  deprecated in its [official model page](https://developers.openai.com/api/docs/models/gpt-5-nano).
  [GPT-4.1 nano](https://developers.openai.com/api/docs/models/gpt-4.1-nano)
  ($0.10/$0.40) is also marked deprecated, so it was not silently substituted.
- [Official current pricing](https://developers.openai.com/api/docs/pricing):
  Luna standard input/output is $0.10/$0.50 per million tokens, rising to
  $0.20/$0.75 above 272K input tokens. Astra is $10/$50, rising to $20/$75.
  Cache writes have separate higher rates; no cache discount is assumed.
- [Luna documentation](https://developers.openai.com/api/docs/models/gpt-6-luna)
  gives a 1,050,000-token context window and supports reasoning `none`.
  [Astra documentation](https://developers.openai.com/api/docs/models/gpt-6-astra)
  gives the same context window and requires reasoning. Both document Chat
  Completions and structured output support. JSON-mode generation remains
  untested; the [JSON-mode guide](https://developers.openai.com/api/docs/guides/structured-outputs#json-mode)
  includes an Astra Chat Completions JSON-object example. These are candidates,
  not a runnable verified configuration.
- The [current model guide](https://developers.openai.com/api/docs/guides/latest-model)
  says temperature is unsupported when reasoning is not `none`; Astra does not
  support `none`. Therefore strongest-model selection and temperature 0 cannot
  both be satisfied. Luna would need explicit `reasoning_effort="none"`, which
  the current client does not send. No parameter was silently dropped.
- Even ignoring that conflict, the existing full-window reservation for Astra
  is at least 1,050,000 × $20 / 1M + 1,024 × $75 / 1M = **$21.0768 per request**,
  already above the total $5 cap. This is a conservative reservation, not an
  estimate of actual short-prompt spend. Cache-write charges, if applicable,
  can increase this further. The corresponding Luna input/output bound is
  $0.210768 per request; 125 worst-case reservations total $26.346 before
  embeddings. Actual usage reconciliation can reduce reservations, but does
  not make an unaffordable Astra request executable.
- Paid evaluation is paused, with **$0 actual spend, $0 reserved**. Options for
  a future scope decision: choose two temperature-compatible models within the
  cap, or explicitly relax temperature and design a proven tighter request
  bound before re-estimating. Neither changes the authorized $5 cap. A larger
  cap alone cannot resolve Astra's temperature conflict. Do not tune questions,
  prompts or k against results when work resumes.

- [text-embedding-3-small pricing](https://developers.openai.com/api/docs/models/text-embedding-3-small)
  remains $0.02 per million input tokens. Unique corpus strings contain
  1,096,009 UTF-8 bytes and the five unique evaluation questions contain 265
  bytes. The existing byte-based token upper bound therefore puts their initial
  embeddings below **$0.021926** (rounded up), before any retries. No embeddings
  were purchased while the generation conflict remains unresolved.

## Approved compatible comparison (2026-10-13)

The user approved replacing the absolute strongest model with a stronger
**temperature-0-compatible** comparison while preserving the total $5 cap.
The selected available pair is `gpt-6-luna` and `gpt-6-sol`, both with explicit
reasoning `none`, temperature 0, JSON-object output and 1,024 output tokens.
Sol is the higher-capability sibling, not Astra or the newer incompatible 6.1.
The prompt, questions and contract-scoped k=5 are unchanged.

[Sol's official model page](https://developers.openai.com/api/docs/models/gpt-6-sol)
verifies reasoning none and rates of $2 input, $0.20 cached input, $2.50 cache
write and $10 output per million tokens. Luna rates are $0.10 / $0.01 / $0.125 /
$0.50. The [model guide](https://developers.openai.com/api/docs/guides/latest-model)
permits temperature with reasoning none. Verified configuration is recorded in
`results/pricing-2026-10-13.json`; copy it to ignored `data/pricing.json` only
while these rates remain current. Both true context limits remain 1,050,000.

For the selected pair, use Responses JSON mode and its official
[exact input-counting endpoint](https://developers.openai.com/api/docs/guides/token-counting).
It counts message framing as well as content. Freeze the counted payload and
send that same payload to generation; do not reuse Responses counts for Chat
Completions or replace them with a character estimate. Reject missing, invalid
or over-10,000 input counts before generation. The 10,000-token request limit
is an enforced application limit, not a fictitious model context limit.
Truncation is disabled. The old Chat Completions path keeps full-window
reservations for other configurations.

Reserve the highest applicable input rate including cache writes. Reconcile
normal, cached and cache-written input separately from API usage. Missing cache
usage retains the full reservation. The existing SQLite ledger is extended
without resetting any request. Automatic retries stay disabled.

With at most 10,000 exactly counted input tokens and 1,024 output tokens per
request, 125 questions per model plus initial corpus/query embeddings have a
conservative ceiling of **$4.647176**, leaving **$0.352824** for smoke/UI checks
or retained uncertain requests. This is conditional on every request passing
the input gate, not a promise that all questions will fit. Every request still
uses the same hard-cap ledger, including CLI/UI calls and explicit retries.

The first capability smoke reached the Responses generation endpoint but
returned HTTP 401 AuthenticationError for `gpt-6-luna`. Model listing and exact
input counting had succeeded. Stop generation, embeddings and retries until
that authentication blocker is resolved; do not change credentials or security
settings. No usage was returned. Retain the **$0.000085125** reservation in the
same ledger; confirmed settled spend is $0, and actual billing for the rejected
request is unknown. No evaluation item has been generated. The installed
OpenAI SDK minimum is now 2.54, which exposes the required counting endpoint;
there is no additional third-party dependency.
