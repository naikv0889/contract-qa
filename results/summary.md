# Evaluation results

The benchmark is fixed at 25 contracts × 5 CUAD categories (125 items), with contract-scoped top-5 retrieval.

| Model | Status | Recall@5 | Refusal accuracy | Grounded answer rate | False refusal rate | Cost (USD) |
| --- | --- | --- | --- | --- | --- | --- |
| gpt-6-luna | Not run | N/A | N/A | N/A | N/A | N/A |
| gpt-6-sol | Not run | N/A | N/A | N/A | N/A | N/A |

N/A means unmeasured or no applicable denominator, not zero performance. Incomplete runs retain per-item data but are not reported as complete benchmark scores.

Recall, grounding and false-refusal denominators include only answerable items. Refusal accuracy includes only items with no annotations. Grounding requires every quote to verify and at least one cited chunk to contain a normalized annotated answer.

Cost is the increase in the shared API budget ledger during that run, including any index creation, query embeddings and generation. Outstanding reservations count conservatively; this is not an invoice. Run models sequentially so unrelated API work does not enter that delta.

Prompts and k are not tuned against these results. Model selection and live measurement require an API key and verified pricing configuration.

Latest checkpoint: the approved pair is `gpt-6-luna` / `gpt-6-sol`. The first
Luna generation smoke returned HTTP 401 AuthenticationError, despite successful
model listing and exact input counting. No evaluation was started. Settled
usage-confirmed spend is **$0**; **$0.000085125** remains reserved for the rejected
request because no usage was returned. Actual billing for that request is
unknown. No embeddings were purchased. See [smoke record](model_smoke.json).
