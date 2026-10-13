# Contract QA

A small Python tool that retrieves contract clauses, asks an OpenAI model to
answer using only those clauses, and checks every quotation in code. Invalid
or missing evidence becomes a refusal. The project makes retrieval, evidence,
and model evaluation inspectable for high-stakes contract workflows. It is an
engineering portfolio project, not legal advice or a production legal tool.

## Current status

The deterministic implementation, 25-contract CUAD subset, and 125-question
evaluation set are included. Live model quality is **not yet measured**:
`OPENAI_API_KEY` was unavailable during construction. No API spending occurred.
See [VALIDATION.md](VALIDATION.md) for measured local checks and
[DECISIONS.md](DECISIONS.md) for deviations from the original brief.

The supplied ingestion and download scripts are preserved unchanged. Chunk
counts and dataset properties are measured from their actual output.

## Repository and CI

Public repository: [naikv0889/contract-qa](https://github.com/naikv0889/contract-qa).
The first four implementation phases passed GitHub Actions CI and were squash
merged: [ingestion #1](https://github.com/naikv0889/contract-qa/pull/1),
[retrieval #2](https://github.com/naikv0889/contract-qa/pull/2),
[verified answers #3](https://github.com/naikv0889/contract-qa/pull/3), and
[evaluation #4](https://github.com/naikv0889/contract-qa/pull/4).
Phase 5, including this UI and documentation, is pending its publication/CI
check at this checkpoint. Follow the [pull requests](https://github.com/naikv0889/contract-qa/pulls)
for its current status. Passing CI does not establish live model quality.

## Quick start: no API key required

Use Python 3.11 or newer. From a checkout of this repository:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
python -m contract_qa.ingest
python scripts/download_cuad.py
python scripts/build_eval.py
```

On Windows activate with `.venv\Scripts\activate`. The selected contract
files, chunks, and evaluation items are committed. Only rebuilding annotations
from the complete CUAD source requires the download step; the original archive
is cached under ignored `data/raw/`. The supplied downloader prints the archive checksum; recorded reference hashes
are in `data/ingest_stats.json`. Check them when refreshing the source. CI runs the offline tests on Python 3.11 for
every push and pull request.

## Enable OpenAI calls

1. Copy `.env.example` to `.env` and set `OPENAI_API_KEY` locally. Never put a
   real key in source code, commits, screenshots, or command arguments.
2. List the models available to that key:
   `python -m contract_qa.budget --list-models`.
3. Consult [official pricing](https://openai.com/api/pricing/) and each
   candidate's official model documentation. Choose the cheapest current
   chat model and the strongest current chat model visible to the key that
   support Chat Completions JSON output and temperature 0. Record choices,
   rates (the highest applicable standard rate across context tiers), input limits,
   documentation URLs, and verification date in
   `DECISIONS.md`. Run `python -m contract_qa.budget --check-models` to
   check the configured IDs against those accessible to the key. Do not substitute a model silently if these options fail.
4. Create ignored `data/pricing.json` with the schema below, replacing every
   placeholder with verified values. Prices are USD per million tokens. The
   example is deliberately not runnable pricing.

```json
{
  "verified_at": "YYYY-MM-DD",
  "source": "https://openai.com/api/pricing/",
  "selected_models": {"cheap": "MODEL_A", "strong": "MODEL_B"},
  "models": {
    "text-embedding-3-small": {
      "input_per_million": "VERIFIED_RATE",
      "output_per_million": 0,
      "max_input_tokens": 8192
    },
    "MODEL_A": {
      "input_per_million": "VERIFIED_RATE",
      "output_per_million": "VERIFIED_RATE",
      "max_input_tokens": "VERIFIED_INTEGER_LIMIT",
      "temperature_zero": true
    },
    "MODEL_B": {
      "input_per_million": "VERIFIED_RATE",
      "output_per_million": "VERIFIED_RATE",
      "max_input_tokens": "VERIFIED_INTEGER_LIMIT",
      "temperature_zero": true
    }
  }
}
```

The configured input limit must be an actual upper bound from model docs, not
an estimate of this project's prompt size. Budget reservations rely on it.
Verify the embedding limit too; the number shown is a placeholder to recheck.

## Budget and cache

The project cap is $10. Every paid request reserves a conservative maximum
charge first; reported usage reconciles that reservation. Unknown or failed
requests keep the reservation, and automatic SDK retries are disabled.
`data/budget.sqlite3` persists spend across runs. To share a single ledger across
clones, set `CONTRACT_QA_BUDGET_PATH` to one absolute persistent file path before
any paid calls. Keep all commands on the same
data directory, never delete/reset the ledger to retry, and do not run other
copies with separate ledgers against the same project budget. This ledger does
not know about unrelated account activity. Billing depends on correct current
pricing configuration, and budget exhaustion can leave evaluation incomplete.

Embeddings are cached by content and model. Re-running an unchanged dataset
reuses vectors, including cached query embeddings. `data/embeddings.npy` and
`data/ids.json` are local generated index artifacts. Do not commit private
contract text or embedding caches if adapting this project to your own data.

## Design and limitations

- **NumPy, not an approximate index:** a full cosine scan is easy to explain
  and test for a small collection. Contract filtering happens before top-k.
- **Flattened filings:** heading candidates in the middle of paragraphs need
  a plausible numbering successor. Article headings can resynchronize the
  sequence. Tables of contents and lettered headings remain limitations.
- **Verifiable offsets:** every chunk is an exact slice of normalized text;
  all non-whitespace normalized text remains covered. Huge paragraphs may
  require a hard split, so a complete annotated span may straddle chunks.
- **Fail-closed evidence:** every quote must occur in its identified retrieved
  chunk after case/whitespace normalization. Empty, fabricated, or unknown
  citations reject the whole answer. This proves quotation provenance, not
  entailment, completeness, or legal correctness.
- **Untrusted contracts:** source clauses are data, not instructions. The
  prompt says to ignore instructions inside them, but code-level quote checks
  cannot eliminate semantic prompt injection.
- **Honest evaluation:** empty CUAD annotations define refusal ground truth
  for the selected categories. Recall and grounding require a full annotated
  span in a single chunk. An annotation can cross boundaries or omit relevant
  interpretations. No tuning on this evaluation set is performed.

## Data and license

The supplied downloader deterministically selects 25 CUAD agreements using
contract-type round-robin sampling and length filters before evaluation.
The Atticus Project supplies CUAD under CC BY 4.0. Source titles and selection are in `data/contracts/manifest.json`; source/script
hashes and measured chunk statistics are in `data/ingest_stats.json`. See [DATA_LICENSE.md](DATA_LICENSE.md)
for attribution and [the official dataset](https://github.com/The-Atticus-Project/cuad).
Code is [MIT licensed](LICENSE). This project has no affiliation with Harvey
or The Atticus Project.

Interview notes: [EXPLAIN.md](EXPLAIN.md). Verified resume wording:
[RESUME.md](RESUME.md).

## Ask a question and compare models

After configuring the key, model choices, and verified pricing:

```sh
python -m contract_qa.retrieve
python -m contract_qa.answer "Which jurisdiction's law governs this agreement?" --contract ABILITYINC_06_15_2020_EX_4_25_SERVICES_AGREEMENT
python scripts/run_eval.py --model MODEL_A
python scripts/run_eval.py --model MODEL_B
python -m contract_qa.budget
```

The two evaluations must run sequentially against the same dataset and ledger.
Their JSON files retain retrieved clauses, verified responses, item-level
scores, benchmark fingerprints, and cost. `results/summary.md` is rebuilt
from measured result files. Failures/checkpoints are labeled incomplete rather
than reported as a completed 125-question evaluation.

### Real output available without the key

The actual answer CLI currently exits with code 2 and this configuration error:

```text
OPENAI_API_KEY is missing. Set it in this environment or .env before API work.
```

A separate offline demonstration uses a real CUAD annotation directly to test
citation validation. It does **not** simulate retrieval or present an answer
as model-generated:

```sh
python scripts/demo_offline.py
```

```text
Offline verification demo; no model or retrieval API was called.
{
  "answer": "Annotated source clause (offline demonstration).",
  "citations": [
    {
      "chunk_id": "AlliedEsportsEntertainmentInc_20190815_8_K_EX_10_34_11788308_EX_10_34_Sponsorship_Agreemen::15.10",
      "quote": "Without reference to choice or conflict of law principles, this Agreement shall be governed by and construed in accordance with the laws of the State of California, USA."
    }
  ]
}
{
  "refusal": "The response could not be verified against the provided clauses."
}
```

## Evaluation results


The benchmark is fixed at 25 contracts × 5 CUAD categories (125 items), with contract-scoped top-5 retrieval.

| Model | Status | Recall@5 | Refusal accuracy | Grounded answer rate | False refusal rate | Cost (USD) |
| --- | --- | --- | --- | --- | --- | --- |
| Cheapest accessible chat model (selection pending) | Not run | N/A | N/A | N/A | N/A | N/A |
| Strongest accessible chat model (selection pending) | Not run | N/A | N/A | N/A | N/A | N/A |

N/A means unmeasured or no applicable denominator, not zero performance. Incomplete runs retain per-item data but are not reported as complete benchmark scores.

Recall, grounding and false-refusal denominators include only answerable items. Refusal accuracy includes only items with no annotations. Grounding requires every quote to verify and at least one cited chunk to contain a normalized annotated answer.

Cost is the increase in the shared API budget ledger during that run, including any index creation, query embeddings and generation. Outstanding reservations count conservatively; this is not an invoice. Run models sequentially so unrelated API work does not enter that delta.

Prompts and k are not tuned against these results. Model selection and live measurement require an API key and verified pricing configuration.

## Browser workspace

```sh
python -m contract_qa.web
```

Open `http://127.0.0.1:8765` in your browser. Pick an agreement, choose a starter
question or write your own, then inspect each verified quote and expand its
full source clause. Use Ctrl+Enter (Windows/Linux) or Command+Enter (macOS) to
submit. The interface works on desktop and narrow screens, supports keyboard
focus, and respects reduced-motion preferences.

The server binds only to localhost by default and never sends the API key to
the browser. A missing key or pricing configuration is a service error, clearly
distinguished from a genuine evidence refusal. With no key, the contract list
and question composer remain available, but no model output is fabricated.
Do not expose this prototype to the public internet; it has no user accounts
or production deployment hardening. Contract contents are sent to OpenAI when
a live question is submitted. This bundled dataset is public; review privacy
requirements before using private contracts.

### Known supplied-script edge case

A strict expected-failure test documents an end-of-file sequence of short
heading-only sections that the unchanged original ingestion script can drop.
The 25 selected contracts pass full non-whitespace coverage checks. The expected
failure is visible rather than hidden; arbitrary new documents require further
review before relying on ingestion. `scripts/inspect_ingest.py` reproduces the
measured heading/chunk statistics without editing the original scripts.
