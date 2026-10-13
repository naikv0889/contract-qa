"""Build the fixed, contract-scoped CUAD evaluation set without using offsets."""

import argparse
import json
from pathlib import Path


QUESTIONS = {
    "Governing Law": "Which jurisdiction's law governs this agreement?",
    "Termination For Convenience": (
        "Can a party terminate this agreement without cause, and if so, how?"
    ),
    "Non-Compete": "Does this agreement restrict any party from competing?",
    "Exclusivity": "Does this agreement grant any exclusive rights?",
    "Cap On Liability": "Does this agreement cap either party's liability?",
}
ROOT = Path(__file__).resolve().parents[1]


def build_items(cuad: dict, manifest: list[dict]) -> list[dict]:
    """Join the selected contracts to the original, named CUAD categories."""
    items = []
    seen_contracts = set()
    by_title = {contract["title"]: contract for contract in cuad["data"]}
    if len(by_title) != len(cuad["data"]):
        raise ValueError("CUAD contains duplicate contract titles")
    for selected in manifest:
        contract_id = selected["contract_id"]
        if contract_id in seen_contracts:
            raise ValueError(f"Duplicate contract_id: {contract_id}")
        seen_contracts.add(contract_id)
        if selected["cuad_title"] not in by_title:
            raise ValueError(f"Manifest title does not match CUAD: {contract_id}")
        contract = by_title[selected["cuad_title"]]
        categories = {}
        for paragraph in contract["paragraphs"]:
            for qa in paragraph["qas"]:
                category = qa["id"].rsplit("__", 1)[-1]
                if category not in QUESTIONS:
                    continue
                if category in categories:
                    raise ValueError(f"Duplicate CUAD category: {contract_id}, {category}")
                texts = [answer["text"] for answer in qa["answers"]]
                if any(not isinstance(text, str) or not text.strip() for text in texts):
                    raise ValueError(f"Empty or invalid annotation: {contract_id}, {category}")
                categories[category] = texts
        for category, question in QUESTIONS.items():
            if category not in categories:
                # Missing metadata is not evidence that a clause is absent.
                raise ValueError(f"Missing CUAD category: {contract_id}, {category}")
            texts = categories[category]
            items.append({
                "id": f"{contract_id}__{category}",
                "contract_id": contract_id,
                "category": category,
                "question": question,
                "annotated_answers": texts,
                "expect_refusal": not texts,
            })
    return items


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "data/raw/CUADv1.json")
    parser.add_argument("--manifest", type=Path, default=ROOT / "data/contracts/manifest.json")
    parser.add_argument("--output", type=Path, default=ROOT / "data/eval.jsonl")
    args = parser.parse_args()
    items = build_items(
        json.loads(args.source.read_text(encoding="utf-8")),
        json.loads(args.manifest.read_text(encoding="utf-8")),
    )
    if len(items) != 125 or len({item["contract_id"] for item in items}) != 25:
        parser.error("The required evaluation set is exactly 25 contracts × 5 categories.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items),
        encoding="utf-8",
    )
    absent = sum(item["expect_refusal"] for item in items)
    print(f"Wrote {len(items)} items ({len(items) - absent} answerable, {absent} absent-clause).")


if __name__ == "__main__":
    main()
