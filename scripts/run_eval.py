"""Measure the frozen CUAD benchmark; never turn API errors into refusals."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def normalize_text(text: str) -> str:
    """Match text, not CUAD's offsets into unnormalized source contracts."""
    return " ".join(text.lower().split())


def contains_annotation(chunk: dict, annotations: list[str]) -> bool:
    text = normalize_text(chunk["text"])
    return any(normalize_text(answer) in text for answer in annotations if answer.strip())


def citations_verified(response: dict, chunks: list[dict]) -> bool:
    """Recheck every citation independently of the answer module."""
    if not isinstance(response, dict) or set(response) != {"answer", "citations"}:
        return False
    if not isinstance(response["answer"], str) or not response["answer"].strip():
        return False
    citations = response["citations"]
    if not isinstance(citations, list) or not citations:
        return False
    by_id = {chunk["chunk_id"]: chunk for chunk in chunks}
    if len(by_id) != len(chunks):
        return False
    for citation in citations:
        if not isinstance(citation, dict) or set(citation) != {"chunk_id", "quote"}:
            return False
        chunk_id, quote = citation["chunk_id"], citation["quote"]
        if not isinstance(chunk_id, str) or not isinstance(quote, str) or not quote.strip():
            return False
        if chunk_id not in by_id or normalize_text(quote) not in normalize_text(by_id[chunk_id]["text"]):
            return False
    return True


def score_item(item: dict, chunks: list[dict], response: dict) -> dict:
    """Score the specified definitions; a verified quote alone is not a gold hit."""
    annotations = item["annotated_answers"]
    if item["expect_refusal"] != (not annotations):
        raise ValueError("expect_refusal must agree with annotated_answers")
    refused = (
        isinstance(response, dict)
        and set(response) == {"refusal"}
        and isinstance(response["refusal"], str)
        and bool(response["refusal"].strip())
    )
    verified = citations_verified(response, chunks)
    gold_ids = {
        chunk["chunk_id"] for chunk in chunks if contains_annotation(chunk, annotations)
    }
    grounded = verified and any(
        citation["chunk_id"] in gold_ids for citation in response["citations"]
    )
    return {
        **item,
        "retrieved": chunks,
        "response": response,
        "retrieval_hit": bool(gold_ids),
        "refused": refused,
        "citations_verified": verified,
        "grounded": grounded,
    }


def summarize(records: list[dict], cost_usd: float) -> dict:
    """Return null, rather than a misleading zero, when a denominator is absent."""
    answerable = [record for record in records if not record["expect_refusal"]]
    absent = [record for record in records if record["expect_refusal"]]

    def fraction(rows: list[dict], key: str):
        return sum(bool(row[key]) for row in rows) / len(rows) if rows else None

    return {
        "evaluated_items": len(records),
        "answerable_items": len(answerable),
        "expect_refusal_items": len(absent),
        "recall_at_5": fraction(answerable, "retrieval_hit"),
        "refusal_accuracy": fraction(absent, "refused"),
        "grounded_answer_rate": fraction(answerable, "grounded"),
        "false_refusal_rate": fraction(answerable, "refused"),
        "cost_usd": cost_usd,
    }


def evaluate_items(items: list[dict], model: str, search_fn, answer_fn):
    """Yield each completed item so the caller can checkpoint paid work."""
    for item in items:
        chunks = search_fn(item["question"], k=5, contract_id=item["contract_id"])
        if len(chunks) > 5 or any(chunk["contract_id"] != item["contract_id"] for chunk in chunks):
            raise ValueError("Retrieval must return at most five chunks from the requested contract")
        response = answer_fn(item["question"], chunks, model=model)
        yield score_item(item, chunks, response)


def model_filename(model: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", model):
        raise ValueError("Model name must contain only letters, numbers, '.', '_' or '-'.")
    return f"{model}.json"


def write_result(path: Path, result: dict) -> None:
    """An atomic checkpoint preserves completed items if a later request fails."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def check_benchmark(results_dir: Path, model: str, fingerprint: str) -> None:
    """Do not pay for a comparison against an older or unverifiable benchmark."""
    for path in results_dir.glob("*.json"):
        report = json.loads(path.read_text(encoding="utf-8"))
        if report.get("status") == "completed" and report.get("model") != model:
            if report.get("benchmark_sha256") != fingerprint:
                raise ValueError(
                    "Saved results use a different or unknown benchmark. "
                    "Use a separate --results-dir for this benchmark."
                )


def write_summary(results_dir: Path, selected_models: dict | None = None) -> str:
    """Include both model roles even before authenticated model selection is possible."""
    results_dir.mkdir(parents=True, exist_ok=True)
    reports = {}
    for path in sorted(results_dir.glob("*.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        if "model" in report and "metrics" in report:
            reports[report["model"]] = report
    hashes = {report.get("benchmark_sha256") for report in reports.values()
              if report["status"] == "completed"}
    incompatible = len(hashes) > 1 or None in hashes
    selected_models = selected_models or {}
    models = list(dict.fromkeys(selected_models.values()))
    models.extend(model for model in reports if model not in models)
    rows = []

    def percent(value):
        return "N/A" if value is None else f"{100 * value:.1f}%"

    for model in models:
        report = reports.get(model)
        if report is None:
            rows.append(f"| {model} | Not run | N/A | N/A | N/A | N/A | N/A |")
            continue
        metric = report["metrics"]
        status = report["status"]
        if status != "completed":
            status = f"Incomplete ({metric['evaluated_items']}/{report['expected_items']})"
            values = ["N/A"] * 4
        elif incompatible:
            status = "Comparison blocked"
            values = ["N/A"] * 4
        else:
            status = f"Completed ({metric['evaluated_items']})"
            values = [percent(metric[key]) for key in (
                "recall_at_5", "refusal_accuracy", "grounded_answer_rate", "false_refusal_rate"
            )]
        rows.append(f"| {model} | {status} | {' | '.join(values)} | ${metric['cost_usd']:.6f} |")
    for role, label in (("cheap", "Cheapest accessible chat model"), ("strong", "Strongest accessible chat model")):
        if role not in selected_models:
            rows.append(f"| {label} (selection pending) | Not run | N/A | N/A | N/A | N/A | N/A |")
    text = "\n".join([
        "# Evaluation results", "",
        "The benchmark is fixed at 25 contracts × 5 CUAD categories (125 items), with contract-scoped top-5 retrieval.", "",
        "| Model | Status | Recall@5 | Refusal accuracy | Grounded answer rate | False refusal rate | Cost (USD) |",
        "| --- | --- | --- | --- | --- | --- | --- |", *rows, "",
        *(["Comparison blocked: completed reports have different or missing benchmark hashes. Keep separate benchmarks in separate results directories.", ""] if incompatible else []),
        "N/A means unmeasured or no applicable denominator, not zero performance. Incomplete runs retain per-item data but are not reported as complete benchmark scores.", "",
        "Recall, grounding and false-refusal denominators include only answerable items. Refusal accuracy includes only items with no annotations. Grounding requires every quote to verify and at least one cited chunk to contain a normalized annotated answer.", "",
        "Cost is the increase in the shared API budget ledger during that run, including any index creation, query embeddings and generation. Outstanding reservations count conservatively; this is not an invoice. Run models sequentially so unrelated API work does not enter that delta.", "",
        "Prompts and k are not tuned against these results. Model selection and live measurement require an API key and verified pricing configuration.", "",
    ])
    (results_dir / "summary.md").write_text(text, encoding="utf-8")
    return text


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--results-dir", type=Path, default=ROOT / "results")
    parser.add_argument("--overwrite", action="store_true", help="Rerun and replace a saved model result (may spend again)")
    args = parser.parse_args()
    try:
        filename = model_filename(args.model)
    except ValueError as error:
        parser.error(str(error))
    output = args.results_dir / filename
    if output.exists() and not args.overwrite:
        parser.error("A result already exists. Use --overwrite to explicitly rerun and spend again.")
    # Import API modules only for a real run; metric tests stay entirely offline.
    from contract_qa.answer import answer_from_chunks
    from contract_qa.budget import Budget, ConfigurationError
    from contract_qa.retrieve import Retriever

    benchmark = (args.data_dir / "eval.jsonl").read_bytes()
    items = [json.loads(line) for line in benchmark.decode("utf-8").splitlines() if line.strip()]
    if len(items) != 125 or len({item["id"] for item in items}) != 125:
        parser.error("Expected 125 unique benchmark items; rebuild data/eval.jsonl.")
    fingerprint = hashlib.sha256(benchmark).hexdigest()
    try:
        check_benchmark(args.results_dir, args.model, fingerprint)
    except ValueError as error:
        parser.error(str(error))
    budget = Budget(args.data_dir)
    before = budget.spent_usd
    result = {
        "model": args.model,
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "expected_items": len(items),
        "benchmark_sha256": fingerprint,
        "k": 5,
        "items": [],
        "metrics": summarize([], 0.0),
    }
    write_result(output, result)
    error_type = None
    try:
        rates = budget.pricing.model(args.model)
        if rates.get("temperature_zero") is not True:
            raise ConfigurationError("Verify model chat JSON mode and temperature=0 before evaluation.")
        retriever = Retriever(data_dir=args.data_dir, budget=budget)
        retriever.build_index()

        def generate(question, chunks, model):
            return answer_from_chunks(question, chunks, model=model, budget=budget)

        for record in evaluate_items(items, args.model, retriever.search, generate):
            result["items"].append(record)
            result["metrics"] = summarize(result["items"], budget.spent_usd - before)
            write_result(output, result)
        result["status"] = "completed"
    except (Exception, KeyboardInterrupt) as error:
        result["status"] = "incomplete"
        error_type = type(error).__name__
        result["error_type"] = error_type
        # Do not record raw provider errors, which may contain request headers.
    finally:
        result["finished_at"] = datetime.now(timezone.utc).isoformat()
        result["metrics"] = summarize(result["items"], budget.spent_usd - before)
        write_result(output, result)
        pricing_path = args.data_dir / "pricing.json"
        try:
            selected = json.loads(pricing_path.read_text(encoding="utf-8")).get("selected_models", {})
        except (OSError, json.JSONDecodeError):
            selected = {}
        write_summary(args.results_dir, selected)
    if error_type:
        parser.exit(1, f"Evaluation incomplete ({error_type}); completed items and cost saved to {output}.\n")
    print(json.dumps(result["metrics"], indent=2))


if __name__ == "__main__":
    main()
